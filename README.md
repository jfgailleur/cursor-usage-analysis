# Cursor usage analysis

CLI tool to analyze AlayaCare Cursor usage exports. Reads a CSV of line-item interactions and outputs one or more summary CSVs based on the chosen analysis.

## Input

A CSV with headers such as:

- **Date** – interaction date
- **User** – user identifier (email); may be `N/A` for bug bot
- **Service Account Name** – used when User is N/A
- **Service Account Kind** – used to filter out `"Errored, No Charge"`
- **Max Mode** – and columns after it that are summed: Input (w/ Cache), Input (w/o Cache), Cache Read, Output Tokens, Total Tokens, Cost

## Behaviour

1. **Filter** – Rows with Service Account Kind = `"Errored, No Charge"` are excluded.
2. **User** – When User is N/A (or empty), the **Service Account Name** is used.
3. **Time periods** – Weeks start on **Monday**.
4. **Aggregation** – Sums the 6 numeric columns (input w/ cache, input w/o, cache read, output token, total tokens, cost) according to the selected analysis.

## Analysis options

| Code | Description | Output file (when using 00) |
|------|-------------|-----------------------------|
| **11** | Per day and per user | `daily_per_user.csv` |
| **12** | Per week (Mon–Sun) and per user | `weekly_per_user.csv` |
| **13** | Per month and per user | `monthly_per_user.csv` |
| **14** | Total per user | `total_per_user.csv` |
| **21** | Per day total (all users) | `daily_total.csv` |
| **22** | Per week total | `weekly_total.csv` |
| **23** | Per month total | `monthly_total.csv` |
| **24** | Grand total (one row) | `total.csv` |
| **00** | Run all of the above into a subfolder | (subfolder with all 8 files) |

## Setup

```bash
cd cursor-usage-analysis
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

```bash
# Show menu and choose interactively (if no -a/-N given)
python analyze.py usage_export.csv

# Run a specific analysis (code as argument or -11, -12, etc.)
python analyze.py usage_export.csv -a 11 -o daily_per_user.csv
python analyze.py usage_export.csv -12 -o weekly_per_user.csv

# Run all analyses into a subfolder
python analyze.py usage_export.csv -a 00 -o ./my_analysis_folder

# Show analysis menu only
python analyze.py --menu
```

- **`-a CODE`** / **`--analysis CODE`**: run analysis `11`, `12`, `13`, `21`, `22`, `23`, `24`, or `00`.
- **`-11`, `-12`, … `-24`, `-00`**: same as `-a 11`, `-a 12`, etc.
- **`-o PATH`**: output file (single analysis) or output directory (for `00`).
- **`-m`** / **`--menu`**: print the analysis menu and exit.

If you omit `-a` and pass only the input file, the script prints the menu and prompts for a choice.

## Repo

https://github.com/jfgailleur/cursor-usage-analysis
