"""
Historical tweet dataset loader.

The source CSV can contain embedded newlines inside the TWEET field.
This module reconstructs logical records before passing them to pandas.

The loader is intentionally streaming-oriented so the full 862k-row dataset
can be processed without loading the raw CSV into memory as one giant string.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterator, Dict, List

EXPECTED_COLUMNS = [
    "TWEET", "STOCK", "DATE", "LAST_PRICE", "1_DAY_RETURN",
    "2_DAY_RETURN", "3_DAY_RETURN", "7_DAY_RETURN", "PX_VOLUME",
    "VOLATILITY_10D", "VOLATILITY_30D", "LSTM_POLARITY",
    "TEXTBLOB_POLARITY",
]

OPTIONAL_COLUMNS = ["MENTION"]


def iter_reconstructed_rows(path: str | Path) -> Iterator[Dict[str, str]]:
    """
    Yield logical rows from the historical tweet CSV.

    A row is considered complete when the parser has encountered enough
    fields for the known schema. This protects against tweets containing
    physical newline characters.
    """
    path = Path(path)
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        buffer: List[str] = []

        for physical_fields in reader:
            if not physical_fields:
                continue

            buffer.extend(physical_fields)

            target = 14 if len(buffer) >= 14 else 13
            if len(buffer) < 13:
                continue

            if len(buffer) >= 14:
                fields = buffer[:14]
                buffer = buffer[14:]
                yield dict(zip(EXPECTED_COLUMNS + OPTIONAL_COLUMNS, fields))
            else:
                fields = buffer[:13]
                buffer = buffer[13:]
                yield dict(zip(EXPECTED_COLUMNS, fields))

        if buffer:
            raise ValueError(
                f"Unparsed trailing fields in {path}: {len(buffer)} values"
            )


def load_csv(path: str | Path, nrows: int | None = None):
    """Load reconstructed records into a pandas DataFrame."""
    import pandas as pd

    rows = []
    for i, row in enumerate(iter_reconstructed_rows(path)):
        rows.append(row)
        if nrows is not None and i + 1 >= nrows:
            break

    df = pd.DataFrame(rows)
    if not df.empty:
        df["DATE"] = pd.to_datetime(df["DATE"], dayfirst=True, errors="coerce")
        numeric = [
            "LAST_PRICE", "1_DAY_RETURN", "2_DAY_RETURN", "3_DAY_RETURN",
            "7_DAY_RETURN", "PX_VOLUME", "VOLATILITY_10D",
            "VOLATILITY_30D", "LSTM_POLARITY", "TEXTBLOB_POLARITY"
        ]
        for col in numeric:
            if col in df:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    return df
