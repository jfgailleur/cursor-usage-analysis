#!/usr/bin/env python3
"""
Cursor usage analysis: aggregate AlayaCare Cursor usage CSV by day/week/month and user or total.
Reads a CSV of line-item interactions, filters out errored/no-charge rows,
normalizes user (email or service account name when N/A), and outputs
CSV(s) according to the selected analysis option.
"""

import argparse
import sys
import time
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

ANALYSIS_OPTIONS = {
    "11": ("Daily per user", "analysis per day and per user total"),
    "12": ("Weekly per user", "analysis per week and per user total (week starts Monday)"),
    "13": ("Monthly per user", "analysis per month and per user total"),
    "14": ("Total per user", "analysis per user total"),
    "21": ("Daily total", "analysis per day total"),
    "22": ("Weekly total", "analysis per week total (week starts Monday)"),
    "23": ("Monthly total", "analysis per month total"),
    "24": ("Grand total", "one row with total for all 6 output columns"),
    "00": ("All analyses", "run all options and write to a subfolder"),
}

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


def _week_monday(series: pd.Series) -> pd.Series:
    """Week start date (Monday) for each date. Week starts on Monday."""
    dt = pd.to_datetime(series, errors="coerce")
    # Monday = 0 in pandas weekday
    monday = dt - pd.to_timedelta(dt.dt.weekday, unit="D")
    return monday.dt.date


def _month_period(series: pd.Series) -> pd.Series:
    """Month as string YYYY-MM."""
    dt = pd.to_datetime(series, errors="coerce")
    # Avoid "dropping timezone" warning when converting to Period
    if dt.dt.tz is not None:
        dt = dt.dt.tz_localize(None)
    return dt.dt.to_period("M").astype(str)


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
    df["_week"] = _week_monday(df[col["date"]])
    df["_month"] = _month_period(df[col["date"]])

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
    empty = df["_user"].isin(("", "nan"))
    if empty.any():
        df.loc[empty, "_user"] = (
            df[sa_col].astype(str).str.strip() if sa_col else "Unknown"
        )

    return df, col


def _get_sum_cols_and_ensure_numeric(df: pd.DataFrame, col: dict[str, str]) -> tuple[list[str], list[str]]:
    """Return (list of actual column names to sum, list of output column names). Ensure numeric."""
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
    for c in sum_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    return sum_cols, out_names


def run_analysis_11(df: pd.DataFrame, col: dict[str, str]) -> pd.DataFrame:
    """Per day and per user total."""
    sum_cols, out_names = _get_sum_cols_and_ensure_numeric(df, col)
    agg = df.groupby(["_day", "_user"], as_index=False)[sum_cols].sum()
    agg.columns = ["date", "user"] + out_names
    return agg


def run_analysis_12(df: pd.DataFrame, col: dict[str, str]) -> pd.DataFrame:
    """Per week (Monday start) and per user total."""
    sum_cols, out_names = _get_sum_cols_and_ensure_numeric(df, col)
    agg = df.groupby(["_week", "_user"], as_index=False)[sum_cols].sum()
    agg.columns = ["week_start_monday", "user"] + out_names
    return agg


def run_analysis_13(df: pd.DataFrame, col: dict[str, str]) -> pd.DataFrame:
    """Per month and per user total."""
    sum_cols, out_names = _get_sum_cols_and_ensure_numeric(df, col)
    agg = df.groupby(["_month", "_user"], as_index=False)[sum_cols].sum()
    agg.columns = ["month", "user"] + out_names
    return agg


def run_analysis_21(df: pd.DataFrame, col: dict[str, str]) -> pd.DataFrame:
    """Per day total (all users)."""
    sum_cols, out_names = _get_sum_cols_and_ensure_numeric(df, col)
    agg = df.groupby("_day", as_index=False)[sum_cols].sum()
    agg.columns = ["date"] + out_names
    return agg


def run_analysis_22(df: pd.DataFrame, col: dict[str, str]) -> pd.DataFrame:
    """Per week total (week starts Monday)."""
    sum_cols, out_names = _get_sum_cols_and_ensure_numeric(df, col)
    agg = df.groupby("_week", as_index=False)[sum_cols].sum()
    agg.columns = ["week_start_monday"] + out_names
    return agg


def run_analysis_23(df: pd.DataFrame, col: dict[str, str]) -> pd.DataFrame:
    """Per month total."""
    sum_cols, out_names = _get_sum_cols_and_ensure_numeric(df, col)
    agg = df.groupby("_month", as_index=False)[sum_cols].sum()
    agg.columns = ["month"] + out_names
    return agg


def run_analysis_14(df: pd.DataFrame, col: dict[str, str]) -> pd.DataFrame:
    """Per user total (all time)."""
    sum_cols, out_names = _get_sum_cols_and_ensure_numeric(df, col)
    agg = df.groupby("_user", as_index=False)[sum_cols].sum()
    agg.columns = ["user"] + out_names
    return agg


def run_analysis_24(df: pd.DataFrame, col: dict[str, str]) -> pd.DataFrame:
    """Single row with grand total for the 6 output columns."""
    sum_cols, out_names = _get_sum_cols_and_ensure_numeric(df, col)
    totals = df[sum_cols].sum()
    out = pd.DataFrame([totals.values], columns=out_names)
    return out


ANALYSIS_RUNNERS = {
    "11": run_analysis_11,
    "12": run_analysis_12,
    "13": run_analysis_13,
    "14": run_analysis_14,
    "21": run_analysis_21,
    "22": run_analysis_22,
    "23": run_analysis_23,
    "24": run_analysis_24,
}

OUTPUT_FILENAMES = {
    "11": "daily_per_user.csv",
    "12": "weekly_per_user.csv",
    "13": "monthly_per_user.csv",
    "14": "total_per_user.csv",
    "21": "daily_total.csv",
    "22": "weekly_total.csv",
    "23": "monthly_total.csv",
    "24": "total.csv",
}


def _empty_result_columns(code: str) -> list[str]:
    if code == "11":
        return ["date", "user"] + SUM_COLUMNS_OUT
    if code == "12":
        return ["week_start_monday", "user"] + SUM_COLUMNS_OUT
    if code == "13":
        return ["month", "user"] + SUM_COLUMNS_OUT
    if code == "14":
        return ["user"] + SUM_COLUMNS_OUT
    if code == "21":
        return ["date"] + SUM_COLUMNS_OUT
    if code == "22":
        return ["week_start_monday"] + SUM_COLUMNS_OUT
    if code == "23":
        return ["month"] + SUM_COLUMNS_OUT
    if code == "24":
        return SUM_COLUMNS_OUT.copy()
    return []


def run_single(df: pd.DataFrame, col: dict[str, str], code: str) -> pd.DataFrame:
    """Run one analysis by code. Returns empty DataFrame with correct columns if df empty."""
    if df.empty and code in ANALYSIS_RUNNERS:
        return pd.DataFrame(columns=_empty_result_columns(code))
    if df.empty:
        return pd.DataFrame()
    return ANALYSIS_RUNNERS[code](df, col)


def run(
    input_path: Path,
    output_path: Path | None,
    analysis: str,
) -> None:
    """Load input CSV, run selected analysis, and write or print output CSV."""
    df, col = load_and_prepare(input_path)
    out = run_single(df, col, analysis)
    if output_path is None:
        out.to_csv(sys.stdout, index=False)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(output_path, index=False)


def run_all(input_path: Path, out_dir: Path) -> None:
    """Run analyses 11, 12, 13, 14, 21, 22, 23, 24 and write each to a file in out_dir."""
    df, col = load_and_prepare(input_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    for code in ("11", "12", "13", "14", "21", "22", "23", "24"):
        out = run_single(df, col, code)
        path = out_dir / OUTPUT_FILENAMES[code]
        out.to_csv(path, index=False)
        print(f"  {path.name}", file=sys.stderr)


def print_menu() -> None:
    print("Analysis options (one output CSV per option):")
    print()
    for code, (title, desc) in ANALYSIS_OPTIONS.items():
        print(f"  {code}: {title} — {desc}")
    print()
    print("Enter code (e.g. 11, 12, 00) or -11, -12 for 11, 12, etc.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze Cursor usage CSV: daily/weekly/monthly per user or total."
    )
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        default=None,
        help="Input CSV file (Cursor usage line items with headers)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output CSV path (default: print to stdout; for 00, a subfolder is created)",
    )
    parser.add_argument(
        "-a",
        "--analysis",
        type=str,
        default=None,
        metavar="CODE",
        help="Analysis code: 11, 12, 13, 14, 21, 22, 23, 24, or 00 for all",
    )
    parser.add_argument(
        "-m",
        "--menu",
        action="store_true",
        help="Show analysis menu and exit",
    )
    args, rest = parser.parse_known_args()

    # Allow -11, -12, -00 etc. as shortcuts for --analysis 11, 12, 00
    for r in rest:
        if r.startswith("-") and r[1:].lstrip("-").isdigit():
            args.analysis = r[1:].lstrip("-")
            break
    if args.analysis is None and not args.menu:
        # Check sys.argv for -NN
        for a in sys.argv[1:]:
            if a.startswith("-") and len(a) >= 2 and (a[1:].isdigit() or (a[1:2] == "-" and a[2:].isdigit())):
                num = a.lstrip("-")
                if num in ("00", "11", "12", "13", "21", "22", "23", "24"):
                    args.analysis = num
                    break
                if len(num) == 2 and num.isdigit():
                    args.analysis = num
                    break

    if args.menu:
        print_menu()
        sys.exit(0)

    valid_codes = set(ANALYSIS_OPTIONS) | set(ANALYSIS_RUNNERS)
    if args.analysis is not None:
        args.analysis = args.analysis.strip()
        if args.analysis not in valid_codes:
            print(f"Error: invalid analysis code '{args.analysis}'. Use: {', '.join(sorted(valid_codes))}", file=sys.stderr)
            sys.exit(1)

    if args.input is None:
        print("Error: input file required. Use: python analyze.py <input.csv> [-a CODE] [-o out.csv]", file=sys.stderr)
        print("Use -m or --menu to see analysis options.", file=sys.stderr)
        sys.exit(1)

    if not args.input.exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    analysis = args.analysis
    if analysis is None:
        print_menu()
        try:
            analysis = input("Choice: ").strip()
        except EOFError:
            analysis = "11"
        if analysis not in valid_codes:
            print(f"Invalid code '{analysis}'. Using 11 (daily per user).", file=sys.stderr)
            analysis = "11"

    if analysis == "00":
        out_dir = args.output or (args.input.parent / f"results_{int(time.time())}")
        print(f"Running all analyses → {out_dir}", file=sys.stderr)
        run_all(args.input, out_dir)
        return

    run(args.input, args.output, analysis)


if __name__ == "__main__":
    main()
