"""
CSV validation and parsing for loan data.
Validates schema, cleans data, and ensures consistency.
"""

import logging
from io import BytesIO
import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ["date", "balance", "rate"]


def parse_csv(file_bytes: bytes, encoding: str = "utf-8") -> pd.DataFrame:
    """
    Parse CSV file bytes into DataFrame.

    Args:
        file_bytes: Raw file content
        encoding: File encoding (default utf-8)

    Returns:
        Raw DataFrame (not cleaned)

    Raises:
        ValueError: If CSV cannot be parsed
    """
    try:
        df = pd.read_csv(BytesIO(file_bytes), encoding=encoding)
        logger.info(f"CSV parsed: {len(df)} rows, {len(df.columns)} columns")
        return df
    except UnicodeDecodeError:
        logger.warning("UTF-8 decoding failed, trying latin-1")
        return pd.read_csv(BytesIO(file_bytes), encoding="latin-1")
    except Exception as e:
        logger.error(f"CSV parse error: {str(e)}")
        raise ValueError(f"Failed to parse CSV: {str(e)}")


def validate_schema(df: pd.DataFrame) -> None:
    """
    Validate that DataFrame has required columns.

    Args:
        df: Input DataFrame

    Raises:
        ValueError: If any required column is missing
    """
    if df.empty:
        raise ValueError("CSV is empty")

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        cols_str = ", ".join(REQUIRED_COLUMNS)
        raise ValueError(
            f"Missing required columns: {', '.join(missing)}. "
            f"Expected: {cols_str}"
        )

    logger.info("Schema validation passed")


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean DataFrame: convert types, drop NaN, sort by date.

    Args:
        df: Input DataFrame

    Returns:
        Cleaned DataFrame

    Raises:
        ValueError: If no valid rows after cleaning
    """
    df_clean = df.copy()

    # Convert types
    try:
        df_clean["date"] = pd.to_datetime(df_clean["date"])
        df_clean["balance"] = pd.to_numeric(df_clean["balance"], errors="coerce")
        df_clean["rate"] = pd.to_numeric(df_clean["rate"], errors="coerce")
    except Exception as e:
        logger.error(f"Type conversion failed: {str(e)}")
        raise ValueError(f"Type conversion error: {str(e)}")

    rows_before = len(df_clean)

    # Drop rows with NaN in required columns
    df_clean = df_clean.dropna(subset=["date", "balance", "rate"])

    if df_clean.empty:
        raise ValueError(
            f"No valid data rows after cleaning (started with {rows_before})"
        )

    rows_dropped = rows_before - len(df_clean)
    logger.info(
        f"Data cleaned: {len(df_clean)} rows valid, {rows_dropped} dropped"
    )

    # Sort by date
    df_clean = df_clean.sort_values("date").reset_index(drop=True)

    return df_clean
