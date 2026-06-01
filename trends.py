#!/usr/bin/env python3
"""
trends.py  -  Multi-year fundamental TRENDS (revenue, earnings, free cash flow).

Why this exists
---------------
A single year's number is easy to misread: 40% earnings growth might just mean
last year was terrible. A multi-year TREND is far more reliable and needs no
valuation theory to read -- "is the line going up or down" is visible to the eye.

What it shows
-------------
For the last few fiscal years: Total Revenue, Net Income, Free Cash Flow,
each with a tiny text bar chart, the year-over-year change, and a neutral,
plain-language read of the trend (e.g. "rising steadily", "turned negative").

What it does NOT do
-------------------
No "buy" / "sell". A rising trend does NOT mean "buy" -- a great company can be
priced so high that all the good news is already in the stock. Trends inform
your understanding; the decision stays yours. Educational, not advice.

Used by trading_bot.py, or run standalone:
    python trends.py --ticker AAPL
    python trends.py --ticker AAPL MSFT NVDA
"""

import argparse

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    yf = None


# Rows we look for in Yahoo's statements (names can vary slightly by ticker)
ROW_ALIASES = {
    "Revenue":        ["Total Revenue", "TotalRevenue", "Revenue"],
    "Net Income":     ["Net Income", "NetIncome", "Net Income Common Stockholders"],
    "Free Cash Flow": ["Free Cash Flow", "FreeCashFlow"],
}


def _find_row(df, aliases):
    """Return the first matching row (a Series indexed by date) or None."""
    if df is None or getattr(df, "empty", True):
        return None
    for name in aliases:
        if name in df.index:
            return df.loc[name]
    return None


def _fmt(x):
    if x is None or (isinstance(x, float) and x != x):  # NaN check
        return "n/a"
    for unit, div in [("T", 1e12), ("B", 1e9), ("M", 1e6)]:
        if abs(x) >= div:
            return f"{x/div:.2f}{unit}"
    return f"{x:.0f}"


def _bar(value, peak, width=18):
    """Tiny ASCII bar; handles negatives by showing them as '<neg>'."""
    if peak == 0 or value is None or value != value:
        return ""
    if value < 0:
        return "<neg>"
    n = int(round(width * value / peak))
    return "#" * max(0, min(width, n))


def _trend_words(values):
    """Neutral description of a sequence (oldest -> newest)."""
    vals = [v for v in values if v is not None and v == v]
    if len(vals) < 2:
        return "not enough data to judge a trend"
    first, last = vals[0], vals[-1]
    rising = sum(1 for a, b in zip(vals, vals[1:]) if b > a)
    falling = sum(1 for a, b in zip(vals, vals[1:]) if b < a)
    steps = len(vals) - 1
    if last < 0 and first >= 0:
        return "turned negative over the period"
    if first <= 0:
        direction = "improved" if last > first else "declined"
        return f"{direction} from a low/negative base (read with care)"
    change = (last - first) / abs(first)
    if rising == steps:
        shape = "rose every year"
    elif falling == steps:
        shape = "fell every year"
    elif rising > falling:
        shape = "rose overall (with a dip)"
    elif falling > rising:
        shape = "fell overall (with a bounce)"
    else:
        shape = "was roughly flat / mixed"
    return f"{shape}; net {change*100:+.0f}% over {steps} year(s)"


def _series_to_years(series, max_years=4):
    """Convert a date-indexed Series to [(year, value), ...] oldest->newest."""
    if series is None:
        return []
    try:
        s = series.dropna()
    except Exception:
        return []
    pairs = []
    for date, val in s.items():
        yr = getattr(date, "year", str(date))
        try:
            pairs.append((yr, float(val)))
        except (TypeError, ValueError):
            continue
    pairs = sorted(pairs, key=lambda p: str(p[0]))   # oldest first
    return pairs[-max_years:]


def show_trends(ticker, income=None, cash=None, max_years=4):
    print(f"\n--- MULTI-YEAR TRENDS: {ticker} ---")
    if yf is None:
        raise SystemExit("Please `pip install yfinance pandas` first.")
    if income is None or cash is None:
        try:
            tk = yf.Ticker(ticker)
            income = tk.income_stmt if income is None else income
            cash = tk.cashflow if cash is None else cash
        except Exception as e:
            print(f"  (could not fetch statements: {e})")
            return

    metrics = {
        "Revenue":        _find_row(income, ROW_ALIASES["Revenue"]),
        "Net Income":     _find_row(income, ROW_ALIASES["Net Income"]),
        "Free Cash Flow": _find_row(cash,   ROW_ALIASES["Free Cash Flow"]),
    }

    any_data = False
    for label, series in metrics.items():
        pairs = _series_to_years(series, max_years)
        if not pairs:
            print(f"\n  {label}: no data available")
            continue
        any_data = True
        peak = max((abs(v) for _, v in pairs), default=0)
        print(f"\n  {label} (oldest -> newest):")
        for yr, val in pairs:
            print(f"    {yr}  {_fmt(val):>10}  {_bar(val, peak)}")
        print(f"    => {_trend_words([v for _, v in pairs])}")

    if not any_data:
        print("\n  No multi-year statement data available for this ticker.")
    print("\n  NOTE: A rising trend is NOT a 'buy' and a falling one is NOT a 'sell'.")
    print("  Trends help you understand the business; the decision is yours.")
    print("  Educational information, not investment advice.")


def main():
    p = argparse.ArgumentParser(description="Multi-year fundamental trends (neutral)")
    p.add_argument("--ticker", nargs="+", required=True)
    p.add_argument("--years", type=int, default=4)
    args = p.parse_args()
    for t in args.ticker:
        show_trends(t, max_years=args.years)


if __name__ == "__main__":
    main()
