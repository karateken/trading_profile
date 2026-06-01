#!/usr/bin/env python3
"""
portfolio.py  -  Read your broker positions CSV, then check & monitor it.

What it does
------------
1. Reads a positions CSV exported from your broker (Symbol/Quantity/cost/etc).
2. Fetches the LATEST price for each holding (Yahoo Finance).
3. Shows current value, gain/loss, and each position's weight in the portfolio.
4. Runs the four strategy signals from trading_bot.py for each holding, so you
   can see at a glance which are in "trend up" vs "trend down" mode TODAY.
5. Flags simple structural facts (concentration, cash %, etc.) -- neutrally.

What it does NOT do
-------------------
No "buy" / "sell", no "your portfolio is good/bad". It surfaces facts and
neutral signals; every decision stays yours. Educational, not advice.

Run it:
    python portfolio.py --csv "Positions-Margin_Universal_Account_5700_-20260530-233949.csv"
    python portfolio.py --csv positions.csv --no-signals      # skip strategy signals (faster)
"""

import argparse
import csv as csvmod
import os
from datetime import datetime

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    yf = None

# Reuse the strategies + signal logic from the bot (same folder).
try:
    from trading_bot import STRATEGIES, build_signal, load_data
    HAVE_BOT = True
except ImportError:
    HAVE_BOT = False


def _f(x, default=0.0):
    """Parse a number from broker CSV; '--' and blanks become default."""
    try:
        return float(str(x).replace(",", "").strip())
    except (ValueError, AttributeError):
        return default


def read_positions(path):
    """Return list of holdings dicts from a broker positions CSV."""
    rows = []
    with open(path, encoding="utf-8-sig") as fh:
        for r in csvmod.DictReader(fh):
            sym = (r.get("Symbol") or "").strip()
            if not sym:
                continue
            rows.append({
                "symbol": sym,
                "name": (r.get("Name") or "").strip(),
                "qty": _f(r.get("Quantity")),
                "cost": _f(r.get("Diluted Cost")),
                "csv_price": _f(r.get("Current price")),
                "csv_mv": _f(r.get("Market Value")),
                "currency": (r.get("Currency") or "").strip(),
            })
    return rows


def latest_price(symbol):
    """Most recent close from Yahoo; falls back to None on failure."""
    if yf is None:
        return None
    try:
        h = yf.Ticker(symbol).history(period="5d")
        if h is not None and not h.empty:
            return float(h["Close"].iloc[-1])
    except Exception:
        pass
    return None


def position_signals(symbol):
    """Return {strategy_name: 'IN'/'OUT'} using the bot's strategies."""
    out = {}
    if not HAVE_BOT:
        return out
    try:
        df = load_data(symbol, "2018-01-01", None)
    except (Exception, SystemExit):
        return {k: "n/a" for k in STRATEGIES}
    for name in STRATEGIES:
        try:
            params = STRATEGIES[name][1]
            sig = build_signal(df, name, **params)
            out[name] = "IN " if sig["raw_pos"].iloc[-1] == 1 else "OUT"
        except Exception:
            out[name] = "n/a"
    return out


def log_snapshot(rows, total_mv, total_pl, total_cost, logfile):
    """
    Append one row PER HOLDING plus a TOTAL row to a history CSV.
    Creates the file with a header if it doesn't exist yet, so you build up
    a time series you can open in Excel later to see how things changed.
    """
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_file = not os.path.exists(logfile)
    header = ["timestamp", "symbol", "quantity", "price",
              "market_value", "pl", "pl_pct", "weight_pct"]
    try:
        with open(logfile, "a", newline="", encoding="utf-8") as fh:
            w = csvmod.writer(fh)
            if new_file:
                w.writerow(header)
            for r in rows:
                weight = (r["mv"] / total_mv * 100) if total_mv else 0
                w.writerow([stamp, r["symbol"], f"{r['qty']:.0f}",
                            f"{r['price']:.2f}", f"{r['mv']:.2f}",
                            f"{r['pl']:.2f}", f"{r['pl_pct']:.2f}",
                            f"{weight:.2f}"])
            tot_pct = (total_pl / total_cost * 100) if total_cost else 0
            w.writerow([stamp, "TOTAL", "", "", f"{total_mv:.2f}",
                        f"{total_pl:.2f}", f"{tot_pct:.2f}", "100.00"])
        print(f"\nSnapshot appended to: {logfile}")
        print("  (open it in Excel to track how your portfolio changes over time)")
    except Exception as e:
        print(f"\n(could not write history log: {e})")


def monitor(path, show_signals=True, logfile=None):
    rows = read_positions(path)
    if not rows:
        raise SystemExit("No positions found in CSV. Check the file.")

    print(f"\nLoaded {len(rows)} positions from:\n  {path}\n")

    # --- pull live prices and compute values ---
    use_live = yf is not None
    for r in rows:
        live = latest_price(r["symbol"]) if use_live else None
        r["price"] = live if live is not None else (r["csv_price"] or 0.0)
        r["live"] = live is not None
        r["mv"] = r["qty"] * r["price"] if r["price"] else r["csv_mv"]
        r["pl"] = (r["price"] - r["cost"]) * r["qty"] if r["cost"] else 0.0
        r["pl_pct"] = ((r["price"] / r["cost"] - 1) * 100
                       if r["cost"] else 0.0)

    total_mv = sum(r["mv"] for r in rows)
    total_pl = sum(r["pl"] for r in rows)
    total_cost = total_mv - total_pl

    any_live = any(r["live"] for r in rows)
    src = "LIVE prices" if any_live else "CSV prices (offline / fetch failed)"
    print(f"=== HOLDINGS ({src}) ===")
    hdr = f"{'Sym':<6}{'Qty':>5}{'Price':>10}{'Value':>11}{'P/L':>11}{'P/L%':>9}{'Weight':>9}"
    print(hdr)
    print("-" * len(hdr))
    for r in sorted(rows, key=lambda x: -x["mv"]):
        w = r["mv"] / total_mv * 100 if total_mv else 0
        flag = "" if r["live"] else " (csv)"
        print(f"{r['symbol']:<6}{r['qty']:>5.0f}{r['price']:>10.2f}"
              f"{r['mv']:>11.2f}{r['pl']:>+11.2f}{r['pl_pct']:>+8.1f}%"
              f"{w:>8.1f}%{flag}")
    print("-" * len(hdr))
    tot_pct = (total_pl / total_cost * 100) if total_cost else 0
    print(f"{'TOTAL':<6}{'':>5}{'':>10}{total_mv:>11.2f}"
          f"{total_pl:>+11.2f}{tot_pct:>+8.1f}%{'100.0%':>9}")

    # --- neutral structural facts ---
    print("\n=== STRUCTURE (neutral facts) ===")
    weights = sorted(((r["mv"] / total_mv * 100 if total_mv else 0), r["symbol"])
                     for r in rows)
    top = weights[-1]
    top2 = sum(w for w, _ in weights[-2:])
    print(f"  Holdings: {len(rows)}   Total value: {total_mv:,.2f}")
    print(f"  Largest position: {top[1]} at {top[0]:.1f}% of invested value")
    print(f"  Top 2 positions: {top2:.1f}% of invested value")
    if top[0] > 25:
        print(f"  -> One position is over 25% of the invested total "
              f"(concentration fact, not a verdict).")
    currencies = set(r["currency"] for r in rows if r["currency"])
    if currencies:
        print(f"  Currencies held: {', '.join(sorted(currencies))}")

    # --- per-position strategy signals ---
    if show_signals and HAVE_BOT and any_live:
        print("\n=== TODAY'S STRATEGY SIGNALS (per holding) ===")
        names = list(STRATEGIES.keys())
        print(f"  {'Sym':<6}" + "".join(f"{n[:11]:<13}" for n in names))
        for r in sorted(rows, key=lambda x: -x["mv"]):
            sigs = position_signals(r["symbol"])
            line = f"  {r['symbol']:<6}" + "".join(
                f"{sigs.get(n, 'n/a'):<13}" for n in names)
            print(line)
        print("\n  IN = strategy would be holding; OUT = would be in cash.")
        print("  These are mechanical signals for learning, NOT buy/sell orders.")
    elif show_signals and not any_live:
        print("\n(Strategy signals need live data - skipped while offline.)")

    if logfile:
        log_snapshot(rows, total_mv, total_pl, total_cost, logfile)

    print("\nNOTE: Facts and neutral signals only. Whether any of this is")
    print("'good' depends on your goals, timeline, and risk tolerance.")
    print("This is educational information, not investment advice.")


def main():
    p = argparse.ArgumentParser(description="Check & monitor a positions CSV")
    p.add_argument("--csv", required=True, help="path to broker positions CSV")
    p.add_argument("--no-signals", action="store_true",
                   help="skip the per-holding strategy signals (faster)")
    p.add_argument("--log", nargs="?", const="portfolio_history.csv", default=None,
                   help="append a snapshot to a history CSV "
                        "(default name: portfolio_history.csv)")
    args = p.parse_args()
    monitor(args.csv, show_signals=not args.no_signals, logfile=args.log)


if __name__ == "__main__":
    main()
