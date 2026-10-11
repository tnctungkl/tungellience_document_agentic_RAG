install:
	python -m pip install -e ".[dev]"

test:
	python -m pytest -q

coverage:
	python -m pytest --cov=app --cov-report=term-missing --cov-report=html

compile:
	python -m compileall app tests

api:
	python -m uvicorn app.api.main:app --reload --host "$${API_HOST:-127.0.0.1}" --port "$${API_PORT:-8000}"

# The browser UI is served by FastAPI; there is no separate Streamlit service.
ui: api

build:
	python scripts/build_index.py

all: compile test coverage
