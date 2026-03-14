"""
generate_pdf_reports.py
-----------------------
Reads every JUnit XML file in reports/ and produces a styled PDF alongside it.
Usage:  python generate_pdf_reports.py
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

REPORTS_DIR = Path("app/tests/reports")

# ── colour palette ──────────────────────────────────────────────────────────
GREEN   = colors.HexColor("#27ae60")
RED     = colors.HexColor("#c0392b")
ORANGE  = colors.HexColor("#e67e22")
BLUE    = colors.HexColor("#2980b9")
DARK    = colors.HexColor("#1a1a2e")
LIGHT   = colors.HexColor("#f4f6f9")
GREY    = colors.HexColor("#7f8c8d")
WHITE   = colors.white
HEADER_BG = colors.HexColor("#2c3e50")


def parse_junit_xml(xml_path: Path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # handle both <testsuites> wrapper and bare <testsuite>
    if root.tag == "testsuites":
        suites = list(root)
    else:
        suites = [root]

    results = []
    for suite in suites:
        for tc in suite.iter("testcase"):
            failure = tc.find("failure")
            error   = tc.find("error")
            skipped = tc.find("skipped")
            if failure is not None:
                status  = "FAILED"
                message = (failure.get("message") or "")[:300]
            elif error is not None:
                status  = "ERROR"
                message = (error.get("message") or "")[:300]
            elif skipped is not None:
                status  = "SKIPPED"
                message = (skipped.get("message") or "")[:300]
            else:
                status  = "PASSED"
                message = ""
            results.append({
                "classname": tc.get("classname", ""),
                "name":      tc.get("name", ""),
                "time":      float(tc.get("time", 0)),
                "status":    status,
                "message":   message,
            })

    total   = len(results)
    passed  = sum(1 for r in results if r["status"] == "PASSED")
    failed  = sum(1 for r in results if r["status"] == "FAILED")
    errors  = sum(1 for r in results if r["status"] == "ERROR")
    skipped = sum(1 for r in results if r["status"] == "SKIPPED")
    duration = sum(r["time"] for r in results)

    return {
        "results":  results,
        "total":    total,
        "passed":   passed,
        "failed":   failed,
        "errors":   errors,
        "skipped":  skipped,
        "duration": duration,
    }


STATUS_HEX = {
    "PASSED":  "#27ae60",
    "FAILED":  "#c0392b",
    "ERROR":   "#e67e22",
    "SKIPPED": "#2980b9",
}


def build_pdf(xml_path: Path, pdf_path: Path):
    data    = parse_junit_xml(xml_path)
    styles  = getSampleStyleSheet()
    module  = xml_path.stem          # e.g. "test_campaigns"

    # ── custom styles ───────────────────────────────────────────────────────
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=22,
        textColor=WHITE,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#bdc3c7"),
        alignment=TA_CENTER,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=DARK,
        spaceBefore=14,
        spaceAfter=6,
    )
    cell_style = ParagraphStyle(
        "Cell",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
    )
    msg_style = ParagraphStyle(
        "Msg",
        parent=styles["Normal"],
        fontSize=7,
        textColor=RED,
        leading=9,
    )

    story = []

    # ── header banner ───────────────────────────────────────────────────────
    overall = "ALL PASSED" if data["failed"] == 0 and data["errors"] == 0 else "FAILURES DETECTED"
    banner_color = GREEN if overall == "ALL PASSED" else RED

    header_data = [[
        Paragraph(f"Test Report — {module}", title_style),
        Paragraph(
            f"Generated: {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}",
            subtitle_style,
        ),
    ]]
    header_table = Table(header_data, colWidths=["100%"])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), HEADER_BG),
        ("TOPPADDING",  (0, 0), (-1, -1), 18),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
        ("LEFTPADDING",  (0, 0), (-1, -1), 20),
        ("RIGHTPADDING", (0, 0), (-1, -1), 20),
        ("ROUNDEDCORNERS", [6, 6, 0, 0]),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.3 * cm))

    # ── summary cards ───────────────────────────────────────────────────────
    summary_data = [[
        Paragraph(f"<b>{data['total']}</b><br/>Total", cell_style),
        Paragraph(f"<b>{data['passed']}</b><br/>Passed", cell_style),
        Paragraph(f"<b>{data['failed']}</b><br/>Failed", cell_style),
        Paragraph(f"<b>{data['errors']}</b><br/>Errors", cell_style),
        Paragraph(f"<b>{data['skipped']}</b><br/>Skipped", cell_style),
        Paragraph(f"<b>{data['duration']:.2f}s</b><br/>Duration", cell_style),
        Paragraph(f"<b>{overall}</b>", ParagraphStyle(
            "StatusCell", parent=cell_style,
            textColor=banner_color, fontSize=9,
        )),
    ]]
    col_w = (A4[0] - 4 * cm) / 7
    summary_table = Table(summary_data, colWidths=[col_w] * 7, rowHeights=[1.4 * cm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), LIGHT),
        ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("BOX",         (0, 0), (-1, -1), 0.5, GREY),
        ("INNERGRID",   (0, 0), (-1, -1), 0.3, GREY),
        ("TOPPADDING",  (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        # colour the status cell background
        ("BACKGROUND",  (1, 0), (1, 0), colors.HexColor("#eafaf1")),  # passed
        ("BACKGROUND",  (2, 0), (2, 0), colors.HexColor("#fdf2f2") if data["failed"] else LIGHT),
        ("BACKGROUND",  (3, 0), (3, 0), colors.HexColor("#fef9e7") if data["errors"] else LIGHT),
        ("BACKGROUND",  (6, 0), (6, 0), colors.HexColor("#eafaf1") if overall == "ALL PASSED" else colors.HexColor("#fdf2f2")),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.4 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=GREY))

    # ── per-test results table ───────────────────────────────────────────────
    story.append(Paragraph("Test Results", section_style))

    th_style = ParagraphStyle("TH", parent=cell_style, textColor=WHITE, fontSize=8)
    table_data = [[
        Paragraph("#",          th_style),
        Paragraph("Test Name",  th_style),
        Paragraph("Class",      th_style),
        Paragraph("Time (s)",   th_style),
        Paragraph("Status",     th_style),
    ]]

    col_widths = [0.8 * cm, 7.5 * cm, 5.5 * cm, 1.8 * cm, 1.8 * cm]

    for i, r in enumerate(data["results"], start=1):
        hex_col = STATUS_HEX.get(r["status"], "#7f8c8d")
        status_para = Paragraph(
            f'<font color="{hex_col}"><b>{r["status"]}</b></font>',
            cell_style,
        )
        row = [
            Paragraph(str(i),          cell_style),
            Paragraph(r["name"],       cell_style),
            Paragraph(r["classname"].split(".")[-1], cell_style),
            Paragraph(f"{r['time']:.3f}", cell_style),
            status_para,
        ]
        table_data.append(row)

        # failure message as extra row
        if r["message"]:
            msg_row = [
                Paragraph("", cell_style),
                Paragraph(r["message"], msg_style),
                Paragraph("", cell_style),
                Paragraph("", cell_style),
                Paragraph("", cell_style),
            ]
            table_data.append(msg_row)

    results_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    row_bg = []
    data_row = 1
    for i, r in enumerate(data["results"], start=1):
        bg = colors.HexColor("#f9f9f9") if i % 2 == 0 else WHITE
        results_table_style = []
        row_bg.append(("BACKGROUND", (0, data_row), (-1, data_row), bg))
        data_row += 1
        if r["message"]:
            row_bg.append(("BACKGROUND", (0, data_row), (-1, data_row), colors.HexColor("#fff5f5")))
            row_bg.append(("SPAN",       (1, data_row), (4, data_row)))
            data_row += 1

    results_table.setStyle(TableStyle([
        # header
        ("BACKGROUND",   (0, 0), (-1, 0), DARK),
        ("TEXTCOLOR",    (0, 0), (-1, 0), WHITE),
        ("FONTSIZE",     (0, 0), (-1, 0), 9),
        ("ROWBACKGROUND",(0, 0), (-1, 0), DARK),
        # grid
        ("BOX",          (0, 0), (-1, -1), 0.5, GREY),
        ("INNERGRID",    (0, 0), (-1, -1), 0.25, colors.HexColor("#e0e0e0")),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("LEFTPADDING",  (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        *row_bg,
    ]))
    story.append(results_table)

    # ── footer note ─────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GREY))
    story.append(Paragraph(
        f"Report generated by pytest + reportlab  •  {module}  •  {datetime.now().strftime('%Y-%m-%d')}",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7, textColor=GREY, alignment=TA_CENTER),
    ))

    # ── build PDF ────────────────────────────────────────────────────────────
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"Test Report — {module}",
        author="pytest-reportlab",
    )
    doc.build(story)
    print(f"  ✅  {pdf_path.name}")


def main():
    xml_files = sorted(REPORTS_DIR.glob("*.xml"))
    if not xml_files:
        print("No XML reports found in reports/. Run run_tests.sh first.")
        return

    print(f"\nGenerating PDF reports from {len(xml_files)} XML file(s)…\n")
    for xml_path in xml_files:
        pdf_path = xml_path.with_suffix(".pdf")
        try:
            build_pdf(xml_path, pdf_path)
        except Exception as exc:
            print(f"  ❌  {xml_path.name}: {exc}")

    print(f"\nDone — reports saved to {REPORTS_DIR}/\n")


if __name__ == "__main__":
    main()
