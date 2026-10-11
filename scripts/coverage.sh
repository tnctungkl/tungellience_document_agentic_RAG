#!/usr/bin/env bash
set -euo pipefail
pytest --cov=app --cov-report=term-missing --cov-report=html
