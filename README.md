# Cursor usage analysis

CLI tool to analyze AlayaCare Cursor usage exports. Reads a CSV of line-item interactions and outputs a daily per-user summary CSV.

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
3. **Aggregation** – For each (date, user), the tool sums: input w/ cache, input w/o, cache read, output token, total tokens, cost.

## Output

CSV with columns:

- `date` (day)
- `user`
- `input w/ cache`
- `input w/o`
- `cache read`
- `output token`
- `total tokens`
- `cost`

## Setup

```bash
cd cursor-usage-analysis
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

```bash
# Print result to stdout
python analyze.py usage_export.csv

# Write to file
python analyze.py usage_export.csv -o daily_usage.csv
```

## Repo

https://github.com/jfgailleur/cursor-usage-analysis
