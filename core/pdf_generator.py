"""
PDF generation for Banker Analytics reports.
Exports Snapshot, Simulator, and Explain narratives to PDF.
Uses reportlab for layout and kaleido/matplotlib for chart images.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from io import BytesIO
from typing import Dict, Any, Optional
import uuid

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    PageBreak,
    Image,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from core.chart_converter import PlotlyConverter

logger = logging.getLogger(__name__)


class PDFGenerator(ABC):
    """Abstract base class for PDF generators."""

    def __init__(self, session_id: str, exports_dir: str = "exports"):
        """
        Initialize PDF generator.

        Args:
            session_id: Session ID for filename
            exports_dir: Directory to save PDFs
        """
        self.session_id = session_id
        self.exports_dir = Path(exports_dir)
        self.exports_dir.mkdir(exist_ok=True)
        self.converter = PlotlyConverter()
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Setup custom reportlab styles for dark theme."""
        # Title style
        self.styles.add(
            ParagraphStyle(
                name="CustomTitle",
                parent=self.styles["Heading1"],
                fontSize=24,
                textColor=HexColor("#00D9FF"),
                spaceAfter=12,
                alignment=TA_CENTER,
            )
        )

        # Section header style
        self.styles.add(
            ParagraphStyle(
                name="SectionHeader",
                parent=self.styles["Heading2"],
                fontSize=16,
                textColor=HexColor("#FFB700"),
                spaceAfter=12,
                spaceBefore=12,
            )
        )

        # Body text
        self.styles.add(
            ParagraphStyle(
                name="CustomBody",
                parent=self.styles["BodyText"],
                fontSize=11,
                textColor=HexColor("#FFFFFF"),
                spaceAfter=12,
            )
        )

        # Small text
        self.styles.add(
            ParagraphStyle(
                name="Small",
                parent=self.styles["Normal"],
                fontSize=9,
                textColor=HexColor("#999999"),
                spaceAfter=6,
            )
        )

    @abstractmethod
    def generate(self) -> str:
        """
        Generate PDF and save to disk.

        Returns:
            Path to generated PDF file
        """
        pass

    def _add_header(
        self,
        story: list,
        title: str,
        session_id: str,
        subtitle: str = "",
    ):
        """Add header section to PDF."""
        story.append(
            Paragraph(title, self.styles["CustomTitle"])
        )
        if subtitle:
            story.append(
                Paragraph(subtitle, self.styles["SectionHeader"])
            )

        header_text = f"Session: {session_id[:12]}... | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        story.append(
            Paragraph(header_text, self.styles["Small"])
        )
        story.append(Spacer(1, 0.2 * inch))

    def _add_footer(self, doc):
        """Add footer with page numbers."""
        # Will be overridden in subclasses if needed
        pass

    def _add_kpi_tiles(self, story: list, kpis: Dict[str, Any]):
        """Add KPI tiles section."""
        story.append(
            Paragraph("Key Performance Indicators", self.styles["SectionHeader"])
        )

        # Create 2x3 grid of KPI tiles
        kpi_data = [
            ["Metric", "Value"],
            ["Start Balance", f"${kpis['start_balance']:,.0f}"],
            ["End Balance", f"${kpis['end_balance']:,.0f}"],
            ["% Change", f"{kpis['pct_change']:.2%}"],
            ["Avg Rate", f"{kpis['avg_rate']:.3%}"],
            ["Rate Change", f"{kpis['rate_change_bps']:.0f} bps"],
        ]

        kpi_table = Table(kpi_data, colWidths=[2.5 * inch, 2.5 * inch])
        kpi_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#003d4d")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#00D9FF")),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 11),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), HexColor("#1a1a2e")),
                    ("TEXTCOLOR", (0, 1), (-1, -1), HexColor("#FFFFFF")),
                    ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                    ("FONTSIZE", (0, 1), (-1, -1), 10),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#1a1a2e"), HexColor("#252541")]),
                    ("GRID", (0, 0), (-1, -1), 1, HexColor("#333333")),
                ]
            )
        )
        story.append(kpi_table)
        story.append(Spacer(1, 0.3 * inch))

    def _add_image(
        self,
        story: list,
        image_bytes: bytes,
        width: float = 5.0,
        title: str = "",
    ):
        """Add image to PDF."""
        if title:
            story.append(
                Paragraph(title, self.styles["SectionHeader"])
            )

        img = Image(BytesIO(image_bytes), width=width * inch)
        story.append(img)
        story.append(Spacer(1, 0.2 * inch))

    def _add_text_section(
        self, story: list, title: str, content: str
    ):
        """Add text section with title."""
        story.append(
            Paragraph(title, self.styles["SectionHeader"])
        )
        story.append(
            Paragraph(content, self.styles["CustomBody"])
        )
        story.append(Spacer(1, 0.2 * inch))

    def _save_pdf(self, story: list, filename: str) -> str:
        """
        Save PDF document to file.

        Args:
            story: List of reportlab Platypus objects
            filename: Filename for PDF

        Returns:
            Path to saved PDF
        """
        filepath = self.exports_dir / filename
        doc = SimpleDocTemplate(
            str(filepath),
            pagesize=letter,
            topMargin=0.5 * inch,
            bottomMargin=0.5 * inch,
        )
        doc.build(story)
        logger.info(f"PDF saved: {filepath} ({filepath.stat().st_size} bytes)")
        return str(filepath)


class SnapshotPDFGenerator(PDFGenerator):
    """Generate PDF for Borrower Snapshot."""

    def __init__(
        self,
        session_id: str,
        df,
        kpis: Dict[str, Any],
        flags: Dict[str, Any],
        balance_chart,
        rate_chart,
        narrative: str,
        exports_dir: str = "exports",
    ):
        """
        Initialize Snapshot PDF generator.

        Args:
            session_id: Session ID
            df: DataFrame with date, balance, rate
            kpis: KPI dict from compute_kpis()
            flags: Risk flags dict from detect_flags()
            balance_chart: Plotly balance chart figure
            rate_chart: Plotly rate chart figure
            narrative: HTML narrative string
            exports_dir: Exports directory
        """
        super().__init__(session_id, exports_dir)
        self.df = df
        self.kpis = kpis
        self.flags = flags
        self.balance_chart = balance_chart
        self.rate_chart = rate_chart
        self.narrative = narrative

    def generate(self) -> str:
        """Generate Snapshot PDF."""
        story = []

        # Header
        self._add_header(
            story,
            "Borrower Snapshot Report",
            self.session_id,
            "Balance and Rate Analysis",
        )

        # KPI Tiles
        self._add_kpi_tiles(story, self.kpis)

        # Charts
        try:
            balance_png = self.converter.figure_to_png(self.balance_chart)
            self._add_image(
                story, balance_png, width=5.0, title="Balance Over Time"
            )
        except Exception as e:
            logger.warning(f"Balance chart export failed: {e}")
            story.append(
                Paragraph(
                    "[Balance chart export failed]",
                    self.styles["Small"],
                )
            )

        try:
            rate_png = self.converter.figure_to_png(self.rate_chart)
            self._add_image(
                story, rate_png, width=5.0, title="Interest Rate Over Time"
            )
        except Exception as e:
            logger.warning(f"Rate chart export failed: {e}")
            story.append(
                Paragraph(
                    "[Rate chart export failed]",
                    self.styles["Small"],
                )
            )

        story.append(PageBreak())

        # Risk Flags
        if any(self.flags.values()):
            self._add_text_section(
                story,
                "Risk Indicators",
                self._format_flags(),
            )

        # Narrative
        self._add_text_section(
            story, "Analysis Summary", self.narrative
        )

        # Generate filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{self.session_id}_snapshot_{timestamp}.pdf"

        return self._save_pdf(story, filename)

    def _format_flags(self) -> str:
        """Format risk flags as text."""
        flags_text = "<br/>".join(
            [
                f"Volatility Spike: {'Yes' if self.flags['volatility_spike'] else 'No'}",
                f"Trend Changed: {'Yes' if self.flags['trend_change'] else 'No'}",
                f"Missing Dates: {'Yes' if self.flags['missing_dates'] else 'No'}",
                f"Outliers: {self.flags['outlier_count']}",
            ]
        )
        return flags_text


class SimulatorPDFGenerator(PDFGenerator):
    """Generate PDF for Scenario & Stress Simulator."""

    def __init__(
        self,
        session_id: str,
        baseline_df,
        results: Dict[str, Any],
        rate_shock_chart,
        balance_shock_chart,
        exports_dir: str = "exports",
    ):
        """
        Initialize Simulator PDF generator.

        Args:
            session_id: Session ID
            baseline_df: Baseline DataFrame
            results: Results dict from run_shocks()
            rate_shock_chart: Plotly rate shock comparison chart
            balance_shock_chart: Plotly balance shock comparison chart
            exports_dir: Exports directory
        """
        super().__init__(session_id, exports_dir)
        self.baseline_df = baseline_df
        self.results = results
        self.rate_shock_chart = rate_shock_chart
        self.balance_shock_chart = balance_shock_chart

    def generate(self) -> str:
        """Generate Simulator PDF."""
        story = []

        # Header
        self._add_header(
            story,
            "Scenario & Stress Analysis Report",
            self.session_id,
            "Rate and Balance Shock Scenarios",
        )

        # Shock parameters
        baseline_end = self.baseline_df["balance"].iloc[-1]
        story.append(
            Paragraph(
                f"Baseline End Balance: ${baseline_end:,.0f}",
                self.styles["CustomBody"],
            )
        )
        story.append(Spacer(1, 0.2 * inch))

        # Charts
        try:
            rate_png = self.converter.figure_to_png(
                self.rate_shock_chart
            )
            self._add_image(
                story,
                rate_png,
                width=5.0,
                title="Rate Shock Scenarios",
            )
        except Exception as e:
            logger.warning(f"Rate shock chart export failed: {e}")

        try:
            balance_png = self.converter.figure_to_png(
                self.balance_shock_chart
            )
            self._add_image(
                story,
                balance_png,
                width=5.0,
                title="Balance Shock Scenarios",
            )
        except Exception as e:
            logger.warning(f"Balance shock chart export failed: {e}")

        story.append(PageBreak())

        # Impact table
        self._add_impact_table(story)

        # Generate filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{self.session_id}_simulator_{timestamp}.pdf"

        return self._save_pdf(story, filename)

    def _add_impact_table(self, story: list):
        """Add impact analysis table."""
        story.append(
            Paragraph(
                "Impact Analysis", self.styles["SectionHeader"]
            )
        )

        # Build impact table from results
        impact_data = [
            ["Scenario", "End Balance (Base)", "End Balance (Shocked)", "Impact %"],
        ]

        for scenario, metrics in self.results.items():
            if scenario != "baseline":
                end_base = metrics.get("end_balance_baseline", 0)
                end_shocked = metrics.get("end_balance_shocked", 0)
                impact_pct = (
                    (end_shocked - end_base) / abs(end_base) * 100
                    if end_base != 0
                    else 0
                )

                impact_data.append(
                    [
                        scenario.replace("_", " ").title(),
                        f"${end_base:,.0f}",
                        f"${end_shocked:,.0f}",
                        f"{impact_pct:+.2f}%",
                    ]
                )

        impact_table = Table(
            impact_data, colWidths=[1.5 * inch, 1.5 * inch, 1.5 * inch, 1 * inch]
        )
        impact_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#003d4d")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#00D9FF")),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), HexColor("#1a1a2e")),
                    ("TEXTCOLOR", (0, 1), (-1, -1), HexColor("#FFFFFF")),
                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#1a1a2e"), HexColor("#252541")]),
                    ("GRID", (0, 0), (-1, -1), 1, HexColor("#333333")),
                ]
            )
        )
        story.append(impact_table)
        story.append(Spacer(1, 0.3 * inch))


class ExplainPDFGenerator(PDFGenerator):
    """Generate PDF for Explain Engine narratives."""

    def __init__(
        self,
        session_id: str,
        explanation: Dict[str, str],
        exports_dir: str = "exports",
    ):
        """
        Initialize Explain PDF generator.

        Args:
            session_id: Session ID
            explanation: Explanation dict with what_matters, what_risks, whats_next
            exports_dir: Exports directory
        """
        super().__init__(session_id, exports_dir)
        self.explanation = explanation

    def generate(self) -> str:
        """Generate Explain PDF."""
        story = []

        # Header
        self._add_header(
            story,
            "Explainable Analytics Narrative",
            self.session_id,
            "AI-Generated Insights",
        )

        # Section 1: What Matters
        self._add_text_section(
            story,
            "What Matters",
            self._extract_text(self.explanation.get("what_matters", "")),
        )

        story.append(PageBreak())

        # Section 2: What Risks
        self._add_text_section(
            story,
            "What Risks",
            self._extract_text(self.explanation.get("what_risks", "")),
        )

        story.append(PageBreak())

        # Section 3: What's Next
        self._add_text_section(
            story,
            "What's Next",
            self._extract_text(self.explanation.get("whats_next", "")),
        )

        # Generate filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{self.session_id}_explain_{timestamp}.pdf"

        return self._save_pdf(story, filename)

    def _extract_text(self, html_text: str) -> str:
        """
        Extract text from HTML narrative.
        Simple extraction: removes HTML tags, preserves content.

        Args:
            html_text: HTML string from explanation

        Returns:
            Plain text for PDF
        """
        import re

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "\n", html_text)
        # Remove extra whitespace
        text = re.sub(r"\n\s*\n", "\n", text)
        # Decode HTML entities
        import html
        text = html.unescape(text)
        return text.strip()
