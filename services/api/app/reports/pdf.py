"""The documentation PDF.

A homeowner shopping for insurance is asked to evidence their mitigation work. This produces that
evidence: the property, the date, the hazard zone and the map it came from, the score and its
working, each finding with the photograph it came from, and completed work with before-and-after
pairs — organised against the *Safer from Wildfires* categories an insurer recognises.

The line this document does not cross is stated on every page: it is a homeowner's own
documentation, not an inspection, not a certification, and not a determination that anyone is
entitled to a discount. Overclaiming here would be the most damaging thing in the product, because
this is the artefact that leaves our hands and gets shown to a third party.

ReportLab rather than an HTML-to-PDF engine: no system libraries, so the container that builds in CI
is the container that renders the report on demo day.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC, datetime

from reportlab.lib import colors as pdf_colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# The categories an insurer recognises under California's Safer from Wildfires framework. Our rules
# map onto these so the document speaks the reader's language rather than ours.
SAFER_FROM_WILDFIRES = {
    "structure": "Class A fire-rated roof, ember-resistant vents, and enclosed eaves",
    "0-5ft": "A five-foot ember-resistant zone around the home",
    "5-30ft": "Defensible space cleared and maintained",
    "30-100ft": "Defensible space cleared and maintained",
}

DISCLAIMER = (
    "This document was produced by the homeowner using Groundwork, an educational tool. It is not "
    "an inspection, a certification, or a determination of eligibility for any insurance discount "
    "or programme. Hazard detections are advisory and were confirmed or dismissed by the "
    "homeowner. "
    "Groundwork provides no evacuation guidance. Verify all requirements with your local fire "
    "agency and your insurer."
)


@dataclass
class ReportPhoto:
    caption: str
    data: bytes


@dataclass
class ReportFinding:
    title: str
    citation: str
    status: str
    zone: str
    severity: str
    rule_status: str
    caveat: str | None
    photo: ReportPhoto | None = None


@dataclass
class ReportData:
    address: str
    label: str | None
    fhsz: str
    fhsz_source_version: str | None
    fire_district: str | None
    score: int
    rulebook_version: str
    applicable_weight: float
    met_weight: float
    outstanding: list[ReportFinding]
    completed: list[ReportFinding]
    generated_at: datetime | None = None


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "GwTitle", parent=base["Title"], fontSize=22, spaceAfter=4, alignment=TA_LEFT
        ),
        "subtitle": ParagraphStyle(
            "GwSubtitle",
            parent=base["Normal"],
            fontSize=11,
            textColor=pdf_colors.HexColor("#5F5C55"),
        ),
        "heading": ParagraphStyle(
            "GwHeading", parent=base["Heading2"], fontSize=14, spaceBefore=16, spaceAfter=6
        ),
        "body": ParagraphStyle("GwBody", parent=base["Normal"], fontSize=10, leading=14),
        "caption": ParagraphStyle(
            "GwCaption",
            parent=base["Normal"],
            fontSize=8,
            textColor=pdf_colors.HexColor("#5F5C55"),
            leading=11,
        ),
        "disclaimer": ParagraphStyle(
            "GwDisclaimer",
            parent=base["Normal"],
            fontSize=7.5,
            textColor=pdf_colors.HexColor("#5F5C55"),
            leading=10,
        ),
    }


def _footer(canvas, doc) -> None:
    """The disclaimer on every page, not just the last one.

    A page of this report will be photographed, emailed, or printed on its own. Whichever page that
    is has to carry the caveat with it.
    """
    canvas.saveState()
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(pdf_colors.HexColor("#7A776F"))
    canvas.drawString(
        0.75 * inch,
        0.55 * inch,
        "Groundwork — homeowner's own documentation. Not an inspection or certification.",
    )
    canvas.drawRightString(LETTER[0] - 0.75 * inch, 0.55 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _finding_block(finding: ReportFinding, styles: dict) -> list:
    rows = [
        Paragraph(f"<b>{finding.title}</b>", styles["body"]),
        Paragraph(
            f"{finding.citation} · zone {finding.zone} · {finding.severity} severity",
            styles["caption"],
        ),
    ]
    if finding.rule_status == "pending_adoption" and finding.caveat:
        rows.append(Paragraph(f"<i>{finding.caveat}</i>", styles["caption"]))
    if finding.photo:
        try:
            image = Image(io.BytesIO(finding.photo.data), width=3.2 * inch, height=2.4 * inch)
            rows.extend([Spacer(1, 4), image, Paragraph(finding.photo.caption, styles["caption"])])
        except Exception:
            rows.append(Paragraph("(photograph could not be embedded)", styles["caption"]))
    rows.append(Spacer(1, 10))
    return [KeepTogether(rows)]


def build_report(data: ReportData) -> bytes:
    """Render the report and return the PDF bytes."""
    styles = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.9 * inch,
        title="Groundwork wildfire mitigation documentation",
        author="Groundwork",
    )

    generated = data.generated_at or datetime.now(UTC)
    story: list = [
        Paragraph("Wildfire mitigation documentation", styles["title"]),
        Paragraph(f"{data.label + ' — ' if data.label else ''}{data.address}", styles["subtitle"]),
        Paragraph(
            f"Prepared {generated.strftime('%d %B %Y')} · rulebook {data.rulebook_version}",
            styles["caption"],
        ),
        Spacer(1, 16),
    ]

    zone_rows = [
        ["Fire hazard severity zone", data.fhsz.replace("_", " ").title()],
        ["Zone source", data.fhsz_source_version or "Not determined"],
        ["Fire district", data.fire_district or "Not determined"],
        ["Readiness score", f"{data.score} / 100"],
        [
            "Score basis",
            f"Meeting {data.met_weight:g} of {data.applicable_weight:g} weighted points "
            f"that apply to this property",
        ],
    ]
    table = Table(zone_rows, colWidths=[2.1 * inch, 4.6 * inch])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), pdf_colors.HexColor("#5F5C55")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, pdf_colors.HexColor("#E0DCD3")),
            ]
        )
    )
    story.append(table)

    story.append(Paragraph("Completed mitigation", styles["heading"]))
    if data.completed:
        story.append(
            Paragraph(
                "Work the homeowner has carried out and marked complete, with the requirement each "
                "addresses.",
                styles["body"],
            )
        )
        story.append(Spacer(1, 8))
        for finding in data.completed:
            story.extend(_finding_block(finding, styles))
    else:
        story.append(Paragraph("No mitigation work has been recorded as complete.", styles["body"]))

    story.append(Paragraph("Safer from Wildfires categories", styles["heading"]))
    story.append(
        Paragraph(
            "How the completed work maps onto the categories used in California's Safer from "
            "Wildfires framework. This mapping is provided for the reader's convenience and is not "
            "a determination that any discount applies.",
            styles["body"],
        )
    )
    story.append(Spacer(1, 6))
    covered = {f.zone for f in data.completed}
    category_rows = [["Category", "Addressed in this document"]]
    for zone, description in SAFER_FROM_WILDFIRES.items():
        category_rows.append([description, "Yes" if zone in covered else "Not yet"])
    category_table = Table(category_rows, colWidths=[4.9 * inch, 1.8 * inch])
    category_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, pdf_colors.HexColor("#E0DCD3")),
            ]
        )
    )
    story.append(category_table)

    if data.outstanding:
        story.append(PageBreak())
        story.append(Paragraph("Outstanding items", styles["heading"]))
        story.append(
            Paragraph(
                "Requirements not yet met at the time this document was prepared. Included "
                "deliberately: a document showing only the good news would not be worth much "
                "to anyone reading it.",
                styles["body"],
            )
        )
        story.append(Spacer(1, 8))
        for finding in data.outstanding:
            story.extend(_finding_block(finding, styles))

    story.append(Spacer(1, 18))
    story.append(Paragraph(DISCLAIMER, styles["disclaimer"]))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
