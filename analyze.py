#!/usr/bin/env python3
"""
Cursor usage analysis: aggregate AlayaCare Cursor usage CSV by day and user.
Reads a CSV of line-item interactions, filters out errored/no-charge rows,
normalizes user (email or service account name when N/A), and outputs
daily per-user sums of token and cost columns.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd


# Output column names (after "Max Mode")
SUM_COLUMNS_OUT = [
    "input w/ cache",
    "input w/o",
    "cache read",
    "output token",
    "total tokens",
    "cost",
]

# Map flexible input header names to our canonical names for summing
INPUT_HEADER_ALIASES = {
    "date": ["date"],
    "user": ["user"],
    "service_account_name": ["service account name"],
    "service_account_kind": ["service account kind", "service acco kind", "service acco"],
    "input_w_cache": [
        "input (w/ cache)",
        "input (w/ cac",
        "input (w/ cache write)",
    ],
    "input_wo_cache": [
        "input (w/o cache)",
        "input (w/o ca",
        "input (w/o cache write)",
    ],
    "cache_read": ["cache read"],
    "output_tokens": ["output token", "output toker", "output tokens"],
    "total_tokens": ["total tokens"],
    "cost": ["cost"],
}


def _normalize_header(s: str) -> str:
    return (s or "").strip().lower()


def _find_column(df: pd.DataFrame, aliases: list[str]) -> str | None:
    """Return the first DataFrame column name that matches any alias (startswith or in)."""
    cols_lower = {c: _normalize_header(c) for c in df.columns}
    for alias in aliases:
        alias_lower = alias.lower()
        for col, norm in cols_lower.items():
            if alias_lower in norm or norm.startswith(alias_lower):
                return col
    return None


def _map_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map our canonical keys to actual CSV column names."""
    mapping = {}
    for key, aliases in INPUT_HEADER_ALIASES.items():
        col = _find_column(df, aliases)
        if col is not None:
            mapping[key] = col
    return mapping


def _parse_date_to_day(series: pd.Series) -> pd.Series:
    """Parse date column to date-only (YYYY-MM-DD)."""
    return pd.to_datetime(series, errors="coerce").dt.date


def load_and_prepare(input_path: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    """Load CSV, normalize columns, filter and prepare for aggregation."""
    df = pd.read_csv(input_path)
    col = _map_columns(df)
    if df.empty:
        return df, col

    for name in ["date", "user", "service_account_kind"]:
        if name not in col:
            raise ValueError(f"Missing required column: {name}")

    # Filter out "Errored, No Charge"
    kind_col = col["service_account_kind"]
    df = df.loc[df[kind_col].astype(str).str.strip().str.lower() != "errored, no charge"].copy()

    # Date as day
    df["_day"] = _parse_date_to_day(df[col["date"]])

    # User: use Service Account Name when User is N/A, empty, or missing
    user_col = col["user"]
    sa_col = col.get("service_account_name")
    if sa_col is not None:
        user_str = df[user_col].astype(str).str.strip().str.upper()
        is_na = user_str.isin(("N/A", "NA", "NAN", "")) | df[user_col].isna()
        df["_user"] = df[user_col].astype(str).where(~is_na, df[sa_col].astype(str))
    else:
        df["_user"] = df[user_col].astype(str)

    df["_user"] = df["_user"].str.strip()
    # If still empty/na after SA substitution, use SA column or "Unknown"
    empty = df["_user"].isin(("", "nan"))
    if empty.any():
        df.loc[empty, "_user"] = (
            df[sa_col].astype(str).str.strip() if sa_col else "Unknown"
        )

    return df, col


def aggregate_by_day_user(df: pd.DataFrame, col: dict[str, str]) -> pd.DataFrame:
    """Group by (day, user) and sum the numeric columns after Max Mode."""
    sum_cols = []
    out_names = []

    for key, out_name in [
        ("input_w_cache", "input w/ cache"),
        ("input_wo_cache", "input w/o"),
        ("cache_read", "cache read"),
        ("output_tokens", "output token"),
        ("total_tokens", "total tokens"),
        ("cost", "cost"),
    ]:
        if key in col:
            sum_cols.append(col[key])
            out_names.append(out_name)

    if not sum_cols:
        raise ValueError("No numeric columns found to sum")

    # Ensure numeric
    for c in sum_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    agg = df.groupby(["_day", "_user"], as_index=False)[sum_cols].sum()
    agg.columns = ["date", "user"] + out_names
    return agg


def run(input_path: Path, output_path: Path | None) -> None:
    """Load input CSV, analyze, and write or print output CSV."""
    df, col = load_and_prepare(input_path)
    if df.empty:
        out = pd.DataFrame(columns=["date", "user"] + SUM_COLUMNS_OUT)
    else:
        out = aggregate_by_day_user(df, col)

    if output_path is None:
        out.to_csv(sys.stdout, index=False)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(output_path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze Cursor usage CSV: daily per-user sums (filter Errored/No Charge, normalize user)."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Input CSV file (Cursor usage line items with headers)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output CSV path (default: print to stdout)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    run(args.input, args.output)


if __name__ == "__main__":
    main()
