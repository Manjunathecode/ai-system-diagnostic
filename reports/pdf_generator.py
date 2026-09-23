"""Readable summaries and complete, paginated tables of sanitized evidence."""
from __future__ import annotations
import os
import re
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle


def _label(value) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(value)).replace("_", " ").strip().capitalize()


def _value(value, key="") -> str:
    if value is None:
        return "Not collected"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)) and "bytes" in key.lower():
        return f"{value / (1024 ** 3):,.2f} GiB ({value:,} bytes)"
    text = str(value)
    if re.match(r"^\d{4}-\d\d-\d\dT", text):
        try:
            return datetime.fromisoformat(text).astimezone().strftime("%d %b %Y, %H:%M %Z")
        except ValueError:
            pass
    return text.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")


def _rows(value, prefix=""):
    """Flatten records without JSON prose, omitting no stored value."""
    if isinstance(value, dict) and value:
        for key, item in value.items():
            yield from _rows(item, f"{prefix} / {_label(key)}" if prefix else _label(key))
    elif isinstance(value, (list, tuple)) and value:
        for index, item in enumerate(value, 1):
            yield from _rows(item, f"{prefix} / {index}")
    else:
        text = "None recorded" if value in ([], {}) else _value(value, prefix)
        for offset in range(0, max(len(text), 1), 500):
            yield [prefix + (" (continued)" if offset else ""), text[offset:offset + 500]]


def _next_action(finding: dict) -> str:
    status = finding.get("status", "not_run")
    if status == "passed":
        return "No action indicated by this check."
    if status in {"not_run", "unavailable", "permission_required", "error"}:
        return "Check the collection error and permissions, then rerun. Health is not established."
    if finding.get("category") == "Disk Health":
        return "Review the affected drive. Consider approved temporary-file cleanup after reviewing scope; rerun the capacity check."
    return "Review the evidence in Issues. Use an available approved workflow or ask an IT technician to investigate."


def export_pdf(report: dict, destination: Path) -> Path:
    font = "Helvetica"
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
    if font_path.is_file():
        if "ReportUI" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("ReportUI", str(font_path)))
        font = "ReportUI"
    body = ParagraphStyle("Evidence", fontName=font, fontSize=9, leading=12, textColor=colors.HexColor("#243447"), spaceAfter=3)
    small = ParagraphStyle("Cell", parent=body, fontSize=8, leading=10)
    heading = ParagraphStyle("Section", parent=body, fontSize=14, leading=18, textColor=colors.HexColor("#125984"), spaceBefore=13, spaceAfter=7, keepWithNext=True)
    title = ParagraphStyle("ReportTitle", parent=heading, fontSize=22, leading=27)
    width = 174 * mm
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(destination), pagesize=A4, leftMargin=18*mm, rightMargin=18*mm,
                            topMargin=16*mm, bottomMargin=19*mm, title=_label(report.get("report_type", "report")))
    story = []

    def paragraph(text, style=body):
        return Paragraph(escape(_value(text)).replace("\n", "<br/>"), style)

    def table(headers, rows, widths=None):
        if not rows:
            story.append(paragraph("No records available."))
            return
        status_colors = {"passed": "#16733B", "resolved": "#16733B", "warning": "#965300", "failed": "#AC2330", "escalated": "#AC2330", "not run": "#66506B", "unavailable": "#66506B", "error": "#AC2330"}
        cells = [[paragraph(cell, ParagraphStyle("Result", parent=small, textColor=colors.HexColor(status_colors[str(cell).lower()]))
                            if str(cell).lower() in status_colors else small) for cell in row] for row in [headers, *rows]]
        t = LongTable(cells, colWidths=widths or [width / len(headers)] * len(headers), repeatRows=1, splitInRow=1, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCEAF3")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7FA")]),
            ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#CCD8E2")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.extend([t, Spacer(1, 8)])

    def section(name):
        story.append(paragraph(name, heading))

    def evidence(value):
        table(["Recorded field", "Evidence"], list(_rows(value)), [width * .38, width * .62])

    story.append(paragraph(report.get("application_name", "AI System Diagnostic"), title))
    story.append(paragraph(_label(report.get("report_type", "Troubleshooting report")), heading))
    if report.get("simulation"):
        story.append(paragraph("SIMULATED REPORT - no real repair was performed.", heading))
    summary = report.get("executive_summary") or {}
    status = report.get("final_status", summary.get("final_status", "Evidence only"))
    table(["Overall outcome", "Meaning"], [[_label(status),
        "Resolution is supported by the recorded verification." if status == "resolved" else
        "Some symptoms remain; review the verification and next actions." if status == "partially_resolved" else
        "Human investigation is required; see escalation details." if status == "escalated" else
        "This report does not establish a successful repair. Recommendations are actions to consider, not completed fixes."]], [width*.3, width*.7])
    table(["Report information", "Value"], [["Generated", _value(report.get("generated_at"))],
        ["Report ID", report.get("report_id", "Not recorded")], ["Source session / scan", report.get("source_id", "Not recorded")],
        ["Application version", report.get("application_version", "Not recorded")], ["Privacy mode", _label(report.get("privacy_mode", "Not recorded"))]], [width*.3, width*.7])
    findings = [item for item in (report.get("diagnostic_findings") or []) if isinstance(item, dict)]
    section("1. At a glance")
    if findings:
        passed = sum(item.get("status") == "passed" for item in findings)
        attention = sum(item.get("status") in {"warning", "failed"} for item in findings)
        table(["Checks recorded", "Passed", "Need attention", "Incomplete / error"], [[len(findings), passed, attention, len(findings)-passed-attention]])
        table(["Check", "Result", "Finding"], [[item.get("name", item.get("category", "Check")), _label(item.get("status", "not_run")), item.get("summary", "No summary recorded")] for item in findings], [width*.24, width*.16, width*.60])
    else:
        story.append(paragraph("No diagnostic findings were recorded for this report. This is not evidence of a healthy system."))
    if report.get("user_reported_problem"):
        table(["User-reported problem", "Detected category"], [[report["user_reported_problem"], report.get("detected_category", "Not established")]], [width*.7, width*.3])
    section("2. Issues and next actions")
    needs = [item for item in findings if item.get("status") != "passed"]
    if needs:
        table(["Issue / check", "Severity", "Recommended next action"], [[item.get("name", "Check"), _label(item.get("severity", "Not recorded")), _next_action(item)] for item in needs], [width*.24, width*.14, width*.62])
    else:
        story.append(paragraph("No action indicated by the recorded checks." if findings else "Run diagnostics to establish the system state."))
    for number, problem in enumerate(report.get("detected_problems") or [], 1):
        if isinstance(problem, dict):
            section(f"Detected problem {number}")
            evidence(problem)
    if report.get("recommended_workflows"):
        evidence({"Approved workflow recommendations": report["recommended_workflows"]})
    if report.get("escalation"):
        section("Escalation - remaining symptoms and human action")
        evidence(report["escalation"])
    section("3. Repair outcome and verification")
    attempts = report.get("fix_attempts") or []
    if attempts:
        table(["Attempt", "Approved workflow", "Recorded outcome"], [[i, a.get("fix_id", a.get("workflow", "Not recorded")), _label(a.get("status", "Not verified"))] for i, a in enumerate(attempts, 1) if isinstance(a, dict)], [width*.12, width*.53, width*.35])
        for i, attempt in enumerate(attempts, 1):
            section(f"Attempt {i}: before, execution, after and verification")
            evidence(attempt)
    elif report.get("report_type") != "repair_attempt":
        story.append(paragraph("No repair attempt is recorded in this report. Diagnostic findings alone cannot confirm a fix."))
    for key in ("before_after_comparison", "verification_evidence", "repair_outcome"):
        if report.get(key):
            section(_label(key))
            evidence(report[key])
    if findings:
        story.append(PageBreak())
        section("4. Detailed diagnostic evidence")
        story.append(paragraph("These tables preserve collected evidence. Redacted values are withheld for privacy. Historical records describe their collection time, not the current system state."))
        for finding in findings:
            section(finding.get("name", "Diagnostic"))
            evidence(finding)
    used = {"application_name", "report_type", "report_id", "generated_at", "source_id", "application_version", "privacy_mode", "final_status", "diagnostic_findings", "user_reported_problem", "detected_category", "detected_problems", "recommended_workflows", "escalation", "fix_attempts", "before_after_comparison", "verification_evidence", "repair_outcome", "simulation", "session_id", "scan_id"}
    remaining = {key: value for key, value in report.items() if key not in used and value not in (None, "", [], {})}
    if remaining:
        section("Additional session evidence and report integrity")
        evidence(remaining)
    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#526477"))
        canvas.drawString(18*mm, 10*mm, "AI System Diagnostic | Local evidence report")
        canvas.drawRightString(A4[0]-18*mm, 10*mm, f"Page {document.page}")
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return destination
