"""
Chart conversion utility for PDF export.
Converts Plotly figures to PNG images for embedding in PDFs.
Primary: Kaleido (native Plotly export)
Fallback: Matplotlib converter
"""

import logging
from typing import Optional
from io import BytesIO

logger = logging.getLogger(__name__)


class PlotlyConverter:
    """Converts Plotly figures to PNG bytes with kaleido/matplotlib fallback."""

    def __init__(self):
        """Initialize converter, check for kaleido availability."""
        self.use_kaleido = self._check_kaleido()
        if self.use_kaleido:
            logger.info("PlotlyConverter: Using kaleido for chart export")
        else:
            logger.warning(
                "PlotlyConverter: Kaleido not available, will use matplotlib fallback"
            )
        self._png_cache = {}  # In-memory cache for converted PNGs

    def _check_kaleido(self) -> bool:
        """Check if kaleido is installed."""
        try:
            import kaleido
            return True
        except ImportError:
            return False

    def figure_to_png(
        self, fig, width: int = 800, height: int = 500
    ) -> bytes:
        """
        Convert Plotly figure to PNG bytes.

        Args:
            fig: Plotly Figure object
            width: PNG width in pixels
            height: PNG height in pixels

        Returns:
            PNG image as bytes

        Raises:
            ValueError: If conversion fails with both methods
        """
        # Try kaleido first (native, fast)
        if self.use_kaleido:
            try:
                png_bytes = fig.to_image(
                    format="png", width=width, height=height
                )
                logger.debug(
                    f"Kaleido export: {width}x{height} → {len(png_bytes)} bytes"
                )
                return png_bytes
            except Exception as e:
                logger.warning(f"Kaleido export failed: {e}, trying matplotlib")
                return self._matplotlib_fallback(fig, width, height)
        else:
            # Use matplotlib fallback
            return self._matplotlib_fallback(fig, width, height)

    def _matplotlib_fallback(
        self, fig, width: int, height: int
    ) -> bytes:
        """
        Convert Plotly figure to PNG using matplotlib.

        Args:
            fig: Plotly Figure object
            width: PNG width in pixels
            height: PNG height in pixels

        Returns:
            PNG image as bytes

        Raises:
            ValueError: If matplotlib conversion fails
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib
            from plotly.io import from_json
            import json

            # Configure matplotlib for dark background (match app theme)
            matplotlib.use("Agg")
            matplotlib.rcParams["figure.facecolor"] = "#0f0f1e"
            matplotlib.rcParams["axes.facecolor"] = "#0f0f1e"
            matplotlib.rcParams["text.color"] = "#ffffff"

            # Create figure
            dpi = 100  # Standard DPI for screen display
            fig_size_inches = (width / dpi, height / dpi)
            mpl_fig, ax = plt.subplots(
                figsize=fig_size_inches, dpi=dpi
            )

            # Extract data from Plotly figure
            if hasattr(fig, "data"):
                for trace in fig.data:
                    if hasattr(trace, "x") and hasattr(trace, "y"):
                        x = trace.x
                        y = trace.y
                        # Plot line or scatter
                        if trace.mode == "lines" or trace.mode == "lines+markers":
                            ax.plot(
                                x,
                                y,
                                marker="o" if "markers" in trace.mode else None,
                                label=trace.name or "",
                                color=trace.line.color
                                if hasattr(trace, "line")
                                else None,
                            )
                        else:
                            ax.scatter(x, y, label=trace.name or "")

            # Add title and labels from Plotly figure
            if hasattr(fig, "layout") and fig.layout.title:
                ax.set_title(
                    fig.layout.title.text,
                    color="#ffffff",
                    fontsize=14,
                    fontweight="bold",
                )
            if hasattr(fig, "layout") and fig.layout.xaxis:
                ax.set_xlabel(
                    fig.layout.xaxis.title.text
                    if fig.layout.xaxis.title
                    else "",
                    color="#ffffff",
                )
            if hasattr(fig, "layout") and fig.layout.yaxis:
                ax.set_ylabel(
                    fig.layout.yaxis.title.text
                    if fig.layout.yaxis.title
                    else "",
                    color="#ffffff",
                )

            # Style axes
            ax.spines["bottom"].set_color("#ffffff")
            ax.spines["left"].set_color("#ffffff")
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.tick_params(colors="#ffffff")
            ax.grid(True, alpha=0.2, color="#ffffff")

            if ax.get_legend():
                ax.legend(facecolor="#0f0f1e", edgecolor="#00d9ff")

            # Save to bytes
            buf = BytesIO()
            mpl_fig.savefig(
                buf,
                format="png",
                dpi=dpi,
                bbox_inches="tight",
                facecolor="#0f0f1e",
            )
            buf.seek(0)
            png_bytes = buf.getvalue()
            buf.close()
            plt.close(mpl_fig)

            logger.debug(
                f"Matplotlib fallback: {width}x{height} → {len(png_bytes)} bytes"
            )
            return png_bytes

        except Exception as e:
            logger.error(f"Matplotlib fallback failed: {e}")
            raise ValueError(
                f"Chart conversion failed (kaleido and matplotlib both failed): {str(e)}"
            )

    def clear_cache(self):
        """Clear PNG cache."""
        self._png_cache.clear()
        logger.debug("PNG cache cleared")
