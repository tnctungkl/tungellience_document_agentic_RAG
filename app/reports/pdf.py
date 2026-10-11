from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.exceptions import RAGApplicationError
from app.validation.schemas import AgentResponse


class ReportGenerationError(RAGApplicationError):
    """Raised when an answer cannot be exported as a report."""


def build_report_pdf(response: AgentResponse) -> bytes:
    """Build a PDF report from a completed agent response."""
    if not response.answer.strip():
        raise ReportGenerationError("A completed answer is required before exporting a report.")

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Tungelligence RAG Analysis Report",
        author="Tungelligence Agentic RAG",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=23,
        textColor=colors.HexColor("#0F172A"),
        alignment=TA_LEFT,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.6,
        leading=14,
        textColor=colors.HexColor("#253041"),
        spaceAfter=6,
    )
    label_style = ParagraphStyle(
        "ReportLabel",
        parent=body_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#64748B"),
    )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    story = [
        Paragraph("Tungelligence", title_style),
        Paragraph("Agentic RAG Analysis Report", body_style),
        Spacer(1, 4 * mm),
    ]

    metadata = [
        [Paragraph("Generated", label_style), Paragraph(generated_at, body_style)],
        [Paragraph("Action", label_style), Paragraph(response.action, body_style)],
        [Paragraph("Confidence", label_style), Paragraph(f"{response.confidence:.2f}", body_style)],
        [Paragraph("Query", label_style), Paragraph(_escape(response.query), body_style)],
    ]
    table = Table(metadata, colWidths=[32 * mm, 135 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F7FB")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#D7DEE8")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E5EAF1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([table, Spacer(1, 8 * mm)])

    story.append(Paragraph("Answer", label_style))
    story.append(Paragraph(_escape(response.answer).replace("\n", "<br/>").strip(), body_style))
    story.append(Spacer(1, 5 * mm))

    if response.rewritten_query:
        story.append(Paragraph("Rewritten Query", label_style))
        story.append(Paragraph(_escape(response.rewritten_query), body_style))
        story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("Sources", label_style))
    if response.citations:
        source_rows = [[
            Paragraph("Source", label_style),
            Paragraph("Score", label_style),
            Paragraph("Chunk", label_style),
        ]]
        for citation in response.citations:
            source_rows.append([
                Paragraph(_escape(citation.source), body_style),
                Paragraph(f"{citation.score:.3f}", body_style),
                Paragraph(_escape(citation.chunk_id), body_style),
            ])
        source_table = Table(source_rows, colWidths=[82 * mm, 25 * mm, 60 * mm], repeatRows=1)
        source_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF7")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(source_table)
    else:
        story.append(Paragraph("No citations were returned for this response.", body_style))

    document.build(story, onFirstPage=_draw_page, onLaterPages=_draw_page)
    return buffer.getvalue()


def _draw_page(canvas, document) -> None:
    """Render a small report footer consistently across pages."""
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#0F172A"))
    canvas.rect(0, 0, A4[0], 8 * mm, stroke=0, fill=1)
    canvas.setFillColor(colors.HexColor("#CBD5E1"))
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(18 * mm, 3 * mm, "Tungelligence Agentic RAG")
    canvas.drawRightString(A4[0] - 18 * mm, 3 * mm, f"Page {document.page}")
    canvas.restoreState()


def _escape(value: str) -> str:
    """Escape user/content text before inserting it into ReportLab Paragraphs."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
