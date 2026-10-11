from pathlib import Path
from uuid import uuid4

import pytest
from pypdf import PdfReader

from app.reports.pdf import ReportGenerationError, build_report_pdf
from app.validation.schemas import AgentResponse, Citation


def make_response() -> AgentResponse:
    return AgentResponse(
        answer="Employees are entitled to 20 days of annual paid leave.",
        action="retrieve",
        query="How many annual leave days do employees have?",
        rewritten_query="annual leave entitlement employees",
        confidence=0.87,
        citations=[
            Citation(source="policy.md", chunk_id=str(uuid4()), score=0.87),
        ],
    )


def test_build_report_pdf_returns_valid_pdf() -> None:
    payload = build_report_pdf(make_response())

    assert payload.startswith(b"%PDF")
    reader = PdfReader(__import__("io").BytesIO(payload))
    assert len(reader.pages) == 1
    assert "Employees are entitled" in reader.pages[0].extract_text()


def test_build_report_pdf_rejects_empty_answer() -> None:
    response = make_response()
    response.answer = "   "

    with pytest.raises(ReportGenerationError):
        build_report_pdf(response)
