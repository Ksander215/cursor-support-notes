import json
import logging
from enum import Enum
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("sec_scanner.exporters")


class ExportFormat(str, Enum):
    PDF = "pdf"
    JSON = "json"
    MARKDOWN = "markdown"


def export_audit_report(
    audit_data: Dict[str, Any],
    result_data: Optional[Dict[str, Any]],
    report_md: Optional[str],
    format: ExportFormat,
) -> Tuple[bytes, str]:
    """
    Export audit report in specified format.
    Returns (content_bytes, content_type).
    """
    if format == ExportFormat.PDF:
        return _export_pdf(audit_data, result_data, report_md)
    elif format == ExportFormat.JSON:
        return _export_json(audit_data, result_data)
    elif format == ExportFormat.MARKDOWN:
        return _export_markdown(audit_data, result_data, report_md)
    else:
        raise ValueError(f"Unsupported export format: {format}")


def _export_pdf(
    audit_data: Dict[str, Any],
    result_data: Optional[Dict[str, Any]],
    report_md: Optional[str],
) -> Tuple[bytes, str]:
    """Export report as PDF using weasyprint"""
    try:
        from weasyprint import HTML, CSS
        from weasyprint.text.fonts import FontConfiguration
    except ImportError:
        logger.error("weasyprint not installed. Install with: pip install weasyprint")
        raise ValueError("PDF export requires weasyprint. Install with: pip install weasyprint")

    # Convert markdown to HTML if available, otherwise generate HTML from data
    if report_md:
        html_content = _markdown_to_html(report_md)
    else:
        html_content = _generate_html_from_data(audit_data, result_data)

    # Add PDF styling
    css = CSS(string=_get_pdf_css())

    # Generate PDF
    font_config = FontConfiguration()
    pdf_bytes = HTML(string=html_content).write_pdf(
        stylesheets=[css], font_config=font_config
    )

    return pdf_bytes, "application/pdf"

    # Convert markdown to HTML if available, otherwise generate HTML from data
    if report_md:
        html_content = _markdown_to_html(report_md)
    else:
        html_content = _generate_html_from_data(audit_data, result_data)

    # Add PDF styling
    css = CSS(string=_get_pdf_css())

    # Generate PDF
    font_config = FontConfiguration()
    pdf_bytes = HTML(string=html_content).write_pdf(
        stylesheets=[css], font_config=font_config
    )

    return pdf_bytes, "application/pdf"


def _export_json(
    audit_data: Dict[str, Any],
    result_data: Optional[Dict[str, Any]],
) -> Tuple[bytes, str]:
    """Export report as JSON"""
    export_data = {
        "audit": {
            "id": audit_data.get("id"),
            "target": audit_data.get("target"),
            "mode": audit_data.get("mode"),
            "status": audit_data.get("status"),
            "created_at": audit_data.get("created_at"),
            "started_at": audit_data.get("started_at"),
            "completed_at": audit_data.get("completed_at"),
            "overall_score": audit_data.get("overall_score"),
            "risk_level": audit_data.get("risk_level"),
        },
        "results": result_data,
        "metadata": {
            "export_format": "json",
            "export_version": "1.0",
        },
    }

    json_bytes = json.dumps(export_data, indent=2, ensure_ascii=False).encode("utf-8")
    return json_bytes, "application/json"


def _export_markdown(
    audit_data: Dict[str, Any],
    result_data: Optional[Dict[str, Any]],
    report_md: Optional[str],
) -> Tuple[bytes, str]:
    """Export report as improved Markdown"""
    if report_md:
        # Enhance existing markdown
        enhanced = _enhance_markdown(report_md, audit_data, result_data)
    else:
        # Generate markdown from data
        enhanced = _generate_markdown_from_data(audit_data, result_data)

    markdown_bytes = enhanced.encode("utf-8")
    return markdown_bytes, "text/markdown; charset=utf-8"


def _markdown_to_html(markdown_text: str) -> str:
    """Convert markdown to HTML"""
    try:
        import markdown
        html_body = markdown.markdown(markdown_text, extensions=["extra", "codehilite"])
        return f"<html><head><meta charset='utf-8'></head><body>{html_body}</body></html>"
    except ImportError:
        # Fallback: simple markdown-like conversion
        html = markdown_text
        # Escape HTML first
        html = html.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # Convert markdown-like syntax
        import re
        html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"`(.+?)`", r"<code>\1</code>", html)
        html = html.replace("\n", "<br>\n")
        return f"<html><head><meta charset='utf-8'></head><body>{html}</body></html>"


def _generate_html_from_data(
    audit_data: Dict[str, Any],
    result_data: Optional[Dict[str, Any]],
) -> str:
    """Generate HTML report from audit data"""
    target = audit_data.get("target", "Unknown")
    score = audit_data.get("overall_score", "N/A")
    risk_level = audit_data.get("risk_level", "N/A")
    created_at = audit_data.get("created_at", "N/A")

    html_parts = [
        "<html><head><meta charset='utf-8'></head><body>",
        f"<h1>Security Audit Report: {target}</h1>",
        f"<p><strong>Date:</strong> {created_at}</p>",
        f"<p><strong>Overall Score:</strong> {score}/100</p>",
        f"<p><strong>Risk Level:</strong> {risk_level}</p>",
    ]

    if result_data:
        categories = result_data.get("categories", {})
        if categories:
            html_parts.append("<h2>Categories</h2><ul>")
            for cat_name, cat_data in categories.items():
                cat_score = cat_data.get("score", "N/A")
                html_parts.append(f"<li><strong>{cat_name}:</strong> {cat_score}/100</li>")
            html_parts.append("</ul>")

        critical_issues = result_data.get("critical_issues", [])
        if critical_issues:
            html_parts.append("<h2>Critical Issues</h2><ul>")
            for issue in critical_issues[:10]:
                html_parts.append(
                    f"<li><strong>{issue.get('category', 'Unknown')}:</strong> "
                    f"{issue.get('issue', 'N/A')} — {issue.get('details', '')}</li>"
                )
            html_parts.append("</ul>")

    html_parts.append("</body></html>")
    return "\n".join(html_parts)


def _enhance_markdown(
    markdown_text: str,
    audit_data: Dict[str, Any],
    result_data: Optional[Dict[str, Any]],
) -> str:
    """Enhance existing markdown with additional metadata"""
    enhanced_parts = [markdown_text]
    enhanced_parts.append("\n---\n")
    enhanced_parts.append("## 📊 Export Information\n")
    enhanced_parts.append(f"- **Audit ID:** `{audit_data.get('id', 'N/A')}`\n")
    enhanced_parts.append(f"- **Export Date:** {audit_data.get('completed_at', 'N/A')}\n")
    
    if result_data:
        categories = result_data.get("categories", {})
        if categories:
            enhanced_parts.append("\n### Category Scores\n")
            for cat_name, cat_data in categories.items():
                cat_score = cat_data.get("score", "N/A")
                enhanced_parts.append(f"- **{cat_name.replace('_', ' ').title()}:** {cat_score}/100\n")
    
    return "".join(enhanced_parts)


def _generate_markdown_from_data(
    audit_data: Dict[str, Any],
    result_data: Optional[Dict[str, Any]],
) -> str:
    """Generate markdown report from audit data"""
    target = audit_data.get("target", "Unknown")
    score = audit_data.get("overall_score", "N/A")
    risk_level = audit_data.get("risk_level", "N/A")
    created_at = audit_data.get("created_at", "N/A")
    audit_id = audit_data.get("id", "N/A")

    md_parts = [
        f"# Security Audit Report: {target}",
        f"**Audit ID:** `{audit_id}`",
        f"**Date:** {created_at}",
        f"**Overall Score:** {score}/100",
        f"**Risk Level:** {risk_level}",
        "",
    ]

    if result_data:
        categories = result_data.get("categories", {})
        if categories:
            md_parts.append("## Category Scores\n")
            for cat_name, cat_data in categories.items():
                cat_score = cat_data.get("score", "N/A")
                md_parts.append(f"- **{cat_name.replace('_', ' ').title()}:** {cat_score}/100")
            md_parts.append("")

        critical_issues = result_data.get("critical_issues", [])
        if critical_issues:
            md_parts.append("## 🚨 Critical Issues\n")
            for issue in critical_issues[:20]:
                md_parts.append(
                    f"- **{issue.get('category', 'Unknown')}:** {issue.get('issue', 'N/A')}"
                )
                if issue.get("details"):
                    md_parts.append(f"  - {issue.get('details')}")
            md_parts.append("")

        recommendations = result_data.get("recommendations", [])
        if recommendations:
            md_parts.append("## 📋 Recommendations\n")
            for i, rec in enumerate(recommendations[:20], 1):
                md_parts.append(f"{i}. {rec}")
            md_parts.append("")

    md_parts.append("---")
    md_parts.append("*Generated by sec-scanner.pro*")
    return "\n".join(md_parts)


def _get_pdf_css() -> str:
    """Get CSS styling for PDF export"""
    return """
        @page {
            size: A4;
            margin: 2cm;
        }
        body {
            font-family: 'DejaVu Sans', Arial, sans-serif;
            font-size: 11pt;
            line-height: 1.6;
            color: #333;
        }
        h1 {
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }
        h2 {
            color: #34495e;
            margin-top: 20px;
            border-bottom: 1px solid #bdc3c7;
            padding-bottom: 5px;
        }
        h3 {
            color: #555;
            margin-top: 15px;
        }
        code {
            background-color: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
        }
        ul, ol {
            margin: 10px 0;
            padding-left: 30px;
        }
        li {
            margin: 5px 0;
        }
        strong {
            color: #2c3e50;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }
        th {
            background-color: #3498db;
            color: white;
        }
        .score-high {
            color: #27ae60;
        }
        .score-medium {
            color: #f39c12;
        }
        .score-low {
            color: #e74c3c;
        }
    """
