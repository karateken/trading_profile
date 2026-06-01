#!/usr/bin/env python3
"""
screener.py  -  Two-step screen: fundamentals (gatekeeper) + technicals (timing).

The idea (educational)
----------------------
Step 1 - FUNDAMENTAL SCREEN decides if a company is even worth considering
         (is it profitable, growing, not drowning in debt, cash-generative).
Step 2 - TECHNICAL SIGNAL decides timing (are the trend strategies "IN" today).

Then each holding lands in ONE of four quadrants:
  PASS  + IN   -> "Good co + uptrend"      (both conditions met)
  PASS  + OUT  -> "Good co, wait"          (quality there, timing not)
  FAIL  + IN   -> "Weak co rising - CAUTION"(the trap pure-technical buys into)
  FAIL  + OUT  -> "Skip"

What it does NOT do
-------------------
No buy/sell calls. The screen is a SIMPLIFIED teaching tool using free data of
limited accuracy. Thresholds are crude and sector-blind. It organizes your
thinking; it does not make decisions. Educational, not investment advice.

Run it:
    python screener.py --csv "positions.csv"
    python screener.py --tickers NVDA MMM TSLA
    python screener.py --csv "positions.csv" --min-pass 3
"""

import argparse
import csv as csvmod

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    from fundamentals import fetch_fundamentals
except ImportError:
    fetch_fundamentals = None

try:
    from trading_bot import STRATEGIES, build_signal, load_data
    HAVE_BOT = True
except ImportError:
    HAVE_BOT = False


def read_tickers_from_csv(path):
    out = []
    with open(path, encoding="utf-8-sig") as fh:
        for r in csvmod.DictReader(fh):
            sym = (r.get("Symbol") or "").strip()
            if sym:
                out.append(sym)
    return out


def fundamental_screen(info):
    """
    Run a simple, transparent set of pass/fail checks on a fundamentals dict.
    Returns (checks, n_pass, n_applicable). Each check: (name, verdict, detail).
    verdict is True/False/None (None = data missing, not counted).
    """
    checks = []

    def add(name, value, test, fmt):
        if value is None or (isinstance(value, float) and value != value):
            checks.append((name, None, "no data"))
        else:
            checks.append((name, bool(test(value)), fmt(value)))

    # Profitable? profit margin > 0
    add("Profitable (margin>0)", info.get("profitMargins"),
        lambda v: v > 0, lambda v: f"margin {v*100:.1f}%")
    # Growing? revenue growth >= 0
    add("Revenue growing (>=0)", info.get("revenueGrowth"),
        lambda v: v >= 0, lambda v: f"rev growth {v*100:.1f}%")
    # Cash-generative? free cash flow > 0
    add("Positive free cash flow", info.get("freeCashflow"),
        lambda v: v > 0, lambda v: f"FCF {v/1e9:.2f}B")
    # Not over-leveraged? debt/equity < 200 (crude, sector-blind)
    add("Debt/Equity < 200", info.get("debtToEquity"),
        lambda v: v < 200, lambda v: f"D/E {v:.0f}")

    n_pass = sum(1 for _, v, _ in checks if v is True)
    n_appl = sum(1 for _, v, _ in checks if v is not None)
    return checks, n_pass, n_appl


def technical_signal(symbol):
    """
    Return (verdict, votes) where verdict is 'IN'/'OUT'/'n/a'.
    Votes = dict of each strategy's latest IN/OUT. IN if majority of
    strategies say IN today.
    """
    if not HAVE_BOT:
        return "n/a", {}
    try:
        df = load_data(symbol, "2018-01-01", None)
    except (Exception, SystemExit):
        return "n/a", {}
    votes = {}
    for name in STRATEGIES:
        try:
            params = STRATEGIES[name][1]
            sig = build_signal(df, name, **params)
            votes[name] = "IN" if sig["raw_pos"].iloc[-1] == 1 else "OUT"
        except Exception:
            votes[name] = "n/a"
    n_in = sum(1 for v in votes.values() if v == "IN")
    n_valid = sum(1 for v in votes.values() if v in ("IN", "OUT"))
    if n_valid == 0:
        return "n/a", votes
    verdict = "IN" if n_in * 2 > n_valid else "OUT"
    return verdict, votes


def quadrant(passes, min_pass, tech, is_etf):
    if is_etf:
        return "ETF - technical only (no company fundamentals)"
    fund_pass = passes >= min_pass
    if tech == "n/a":
        return "Good co, timing n/a" if fund_pass else "Skip (fails screen)"
    if fund_pass and tech == "IN":
        return ">>> Good co + uptrend"
    if fund_pass and tech == "OUT":
        return "Good co, WAIT (timing not yet)"
    if not fund_pass and tech == "IN":
        return "!!! Weak co RISING - caution (the trap)"
    return "Skip (fails screen, no trend)"


def run(tickers, min_pass=3):
    if yf is None:
        print("Please `pip install yfinance` first.")
    print(f"\nTwo-step screen  (fundamental gate: need >= {min_pass} of 4 checks)\n")

    for sym in tickers:
        is_etf = False
        print(f"================  {sym}  ================")

        # ---- Step 1: fundamentals ----
        info = fetch_fundamentals(sym) if fetch_fundamentals else {}
        # ETFs/commodities often have no company fundamentals
        if not info or info.get("quoteType") in ("ETF", "MUTUALFUND"):
            is_etf = True
            print("  STEP 1 (fundamentals): n/a - looks like an ETF/fund")
            checks, passes = [], 0
        else:
            checks, passes, appl = fundamental_screen(info)
            print(f"  STEP 1 (fundamentals): {passes}/{len(checks)} checks pass")
            for name, verdict, detail in checks:
                mark = "PASS" if verdict is True else ("FAIL" if verdict is False else "----")
                print(f"      [{mark}] {name:<26} {detail}")

        # ---- Step 2: technicals ----
        tech, votes = technical_signal(sym)
        if votes:
            vote_str = "  ".join(f"{k.split('_')[0][:4]}:{v}" for k, v in votes.items())
            print(f"  STEP 2 (technical): {tech}   ({vote_str})")
        else:
            print(f"  STEP 2 (technical): {tech}")

        # ---- Verdict quadrant ----
        q = quadrant(passes, min_pass, tech, is_etf)
        print(f"  => QUADRANT: {q}\n")

    print("Legend: 'Good co + uptrend' = both met | 'WAIT' = quality but no trend")
    print("        'CAUTION/trap' = rising but weak fundamentals | 'Skip' = neither")
    print("\nNOTE: Simplified educational screen on free data. Thresholds are crude")
    print("and sector-blind. This organizes thinking; it makes no buy/sell call.")
    print("Not investment advice.")


def main():
    p = argparse.ArgumentParser(description="Two-step fundamental + technical screen")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--csv", help="positions CSV to read tickers from")
    g.add_argument("--tickers", nargs="+", help="explicit list of tickers")
    p.add_argument("--min-pass", type=int, default=3,
                   help="how many of the 4 fundamental checks must pass (default 3)")
    args = p.parse_args()
    tickers = read_tickers_from_csv(args.csv) if args.csv else args.tickers
    run(tickers, min_pass=args.min_pass)


if __name__ == "__main__":
    main()
