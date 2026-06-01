#!/usr/bin/env python3
"""
fundamentals.py  -  Auto-collect and DISPLAY company fundamentals.

What it does
------------
Pulls common fundamental metrics for a stock (P/E, growth, margins, debt, etc.)
from Yahoo Finance, lays them out neatly, and prints a NEUTRAL one-line guide
for how each metric is generally read.

What it deliberately does NOT do
--------------------------------
It does NOT output "buy" or "sell". Whether a number is good depends on the
industry, growth rate, interest rates, and YOUR goals -- no formula decides
that for you. This tool gathers and explains; the judgement stays with you.
This is educational information, not investment advice.

Used by trading_bot.py, or run standalone:
    python fundamentals.py --ticker AAPL
    python fundamentals.py --ticker AAPL MSFT NVDA
"""

import argparse

try:
    import yfinance as yf
except ImportError:
    yf = None


# Each metric: (info_key, label, formatter, neutral interpretation note)
def _pct(x):  return f"{x*100:.1f}%" if isinstance(x, (int, float)) else "n/a"
def _num(x):  return f"{x:.2f}"      if isinstance(x, (int, float)) else "n/a"
def _big(x):
    if not isinstance(x, (int, float)): return "n/a"
    for unit, div in [("T", 1e12), ("B", 1e9), ("M", 1e6)]:
        if abs(x) >= div: return f"{x/div:.2f}{unit}"
    return f"{x:.0f}"

METRICS = [
    ("trailingPE",     "Trailing P/E",     _num,
     "price vs past earnings; high = pricey OR high-growth expectations"),
    ("forwardPE",      "Forward P/E",      _num,
     "price vs expected earnings; compare to the trailing P/E and to peers"),
    ("pegRatio",       "PEG ratio",        _num,
     "P/E adjusted for growth; ~1 often seen as 'fair', but rough"),
    ("priceToBook",    "Price/Book",       _num,
     "price vs net assets; matters more for banks/asset-heavy firms"),
    ("profitMargins",  "Profit margin",    _pct,
     "profit per dollar of sales; higher = more efficient, varies by industry"),
    ("returnOnEquity", "Return on equity", _pct,
     "profit generated on shareholder capital; higher is generally better"),
    ("revenueGrowth",  "Revenue growth",   _pct,
     "year-over-year sales growth; negative = shrinking top line"),
    ("earningsGrowth", "Earnings growth",  _pct,
     "year-over-year profit growth; volatile, check multi-year trend too"),
    ("debtToEquity",   "Debt/Equity",      _num,
     "leverage; high = more risk if business slows, but norms differ by sector"),
    ("currentRatio",   "Current ratio",    _num,
     "short-term assets vs liabilities; below 1 can signal liquidity strain"),
    ("dividendYield",  "Dividend yield",   _pct,
     "annual dividend vs price; 0 is normal for growth firms"),
    ("freeCashflow",   "Free cash flow",   _big,
     "cash left after capex; positive and growing is generally healthy"),
    ("marketCap",      "Market cap",       _big,
     "total company size"),
]


def fetch_fundamentals(ticker: str) -> dict:
    """Return Yahoo's info dict for a ticker (empty dict on failure)."""
    if yf is None:
        raise SystemExit("Please `pip install yfinance` first.")
    try:
        info = yf.Ticker(ticker).info
        return info if isinstance(info, dict) else {}
    except Exception as e:
        print(f"  (could not fetch fundamentals for {ticker}: {e})")
        return {}


def show_fundamentals(ticker: str, info: dict | None = None):
    if info is None:
        info = fetch_fundamentals(ticker)
    print(f"\n--- FUNDAMENTALS: {ticker} ---")
    if not info:
        print("  No fundamental data available.")
        return
    name = info.get("longName", ticker)
    sector = info.get("sector", "n/a")
    industry = info.get("industry", "n/a")
    print(f"  {name}")
    print(f"  Sector: {sector}   Industry: {industry}\n")
    print(f"  {'Metric':<18}{'Value':<12}How it's generally read")
    print(f"  {'-'*18}{'-'*12}{'-'*44}")
    for key, label, fmt, note in METRICS:
        val = fmt(info.get(key))
        print(f"  {label:<18}{val:<12}{note}")
    print("\n  NOTE: These are facts + neutral guides, NOT a buy/sell call.")
    print("  Whether a number is 'good' depends on the industry, growth,")
    print("  interest rates, and your own goals. You decide. Not advice.")


def main():
    p = argparse.ArgumentParser(description="Show company fundamentals (neutral)")
    p.add_argument("--ticker", nargs="+", required=True)
    args = p.parse_args()
    for t in args.ticker:
        show_fundamentals(t)


if __name__ == "__main__":
    main()
