#!/usr/bin/env python3
"""
watchlist.py  -  Take-profit / stop-loss MONITOR + optional news sentiment.

What it does
------------
1. Reads your holdings from a broker positions CSV (symbols + cost basis).
2. For each, computes a TAKE-PROFIT price (default +3%) and a STOP-LOSS price
   (default -2%, you can set 1.5-2%), relative to an anchor price.
3. Fetches the latest price and FLAGS whether take-profit or stop-loss is hit.
4. (Optional) Pulls recent news + a sentiment score per stock from Finnhub,
   if you supply a free API key, to help you UNDERSTAND the stock.

Anchor choice (important):
  --anchor cost     thresholds measured from your ORIGINAL buy price (default)
  --anchor current  treat TODAY'S price as a fresh entry, then measure from it
  (Use 'current' for a brand-new position; 'cost' for tracking an existing one.
   For positions already far in profit, 'cost' thresholds are long in the past.)

What it does NOT do
-------------------
It does NOT place or auto-execute any orders. It does NOT tell you to buy or
sell. It shows prices, threshold flags, and news facts; YOU decide and YOU
place any trade yourself in your broker. Educational, not investment advice.

Run it:
    python watchlist.py --csv "positions.csv"
    python watchlist.py --csv "positions.csv" --take 3 --stop 1.5
    python watchlist.py --csv "positions.csv" --anchor current --stop 2
    python watchlist.py --csv "positions.csv" --news --finnhub-key YOUR_KEY
"""

import argparse
import csv as csvmod
import os

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    import finnhub  # optional; only needed for --news
except ImportError:
    finnhub = None


def _f(x, default=0.0):
    try:
        return float(str(x).replace(",", "").strip())
    except (ValueError, AttributeError):
        return default


def read_positions(path):
    rows = []
    with open(path, encoding="utf-8-sig") as fh:
        for r in csvmod.DictReader(fh):
            sym = (r.get("Symbol") or "").strip()
            if not sym:
                continue
            rows.append({
                "symbol": sym,
                "cost": _f(r.get("Diluted Cost")),
                "csv_price": _f(r.get("Current price")),
                "qty": _f(r.get("Quantity")),
            })
    return rows


def latest_price(symbol):
    try:
        from data_source import latest_price as ds_price
        p = ds_price(symbol)
        if p:
            return p
    except ImportError:
        pass
    if yf is None:
        return None
    try:
        h = yf.Ticker(symbol).history(period="5d")
        if h is not None and not h.empty:
            return float(h["Close"].iloc[-1])
    except Exception:
        pass
    return None


def recent_news(symbol, client, days=7, limit=5):
    """
    Return a list of recent news items (headline + source + url) from Finnhub's
    company_news endpoint, which is available on the free tier.
    Returns [] on no data, or [{'error': ...}] on failure.
    """
    if client is None:
        return []
    from datetime import datetime, timedelta
    to = datetime.now().date()
    frm = to - timedelta(days=days)
    try:
        items = client.company_news(symbol,
                                    _from=frm.isoformat(),
                                    to=to.isoformat()) or []
        out = []
        for it in items[:limit]:
            out.append({
                "headline": (it.get("headline") or "").strip(),
                "source": (it.get("source") or "").strip(),
                "url": (it.get("url") or "").strip(),
            })
        return out
    except Exception as e:
        return [{"error": str(e)}]


def monitor(path, take=3.0, stop=2.0, anchor="cost",
            use_news=False, finnhub_key=None):
    rows = read_positions(path)
    if not rows:
        raise SystemExit("No positions found in CSV. Check the file.")

    print(f"\nWatchlist from: {path}")
    print(f"Take-profit: +{take:.2f}%   Stop-loss: -{stop:.2f}%   "
          f"Anchor: {anchor}\n")

    # set up Finnhub client only if requested
    client = None
    if use_news:
        if finnhub is None:
            print("(--news needs the finnhub package: pip install finnhub-python)\n")
        elif not finnhub_key:
            print("(--news needs --finnhub-key YOUR_KEY from finnhub.io)\n")
        else:
            try:
                client = finnhub.Client(api_key=finnhub_key)
            except Exception as e:
                print(f"(could not start Finnhub client: {e})\n")

    hdr = (f"{'Sym':<6}{'Now':>9}{'Anchor':>9}{'TP@':>9}{'SL@':>9}"
           f"{'Chg%':>8}  Status")
    print(hdr)
    print("-" * len(hdr))

    for r in rows:
        live = latest_price(r["symbol"])
        now = live if live is not None else r["csv_price"]
        base = now if anchor == "current" else (r["cost"] or now)
        if not base:
            print(f"{r['symbol']:<6}  (no anchor price available)")
            continue
        tp = base * (1 + take / 100.0)
        sl = base * (1 - stop / 100.0)
        chg = (now / base - 1) * 100 if base else 0.0

        if now >= tp:
            status = ">>> TAKE-PROFIT reached (you set +{:.2f}%)".format(take)
        elif now <= sl:
            status = ">>> STOP-LOSS reached (you set -{:.2f}%)".format(stop)
        else:
            status = "within range"
        tag = "" if live is not None else " (csv price)"

        print(f"{r['symbol']:<6}{now:>9.2f}{base:>9.2f}{tp:>9.2f}{sl:>9.2f}"
              f"{chg:>+7.2f}%  {status}{tag}")

    # ---- optional recent-news block (headlines + links) ----
    if client is not None:
        print("\n=== RECENT NEWS HEADLINES (Finnhub, last 7 days) ===")
        for r in rows:
            items = recent_news(r["symbol"], client)
            print(f"\n  {r['symbol']}:")
            if not items:
                print("    (no recent news found - ETFs like GLD often have none)")
                continue
            if isinstance(items[0], dict) and "error" in items[0]:
                print(f"    (no data: {items[0]['error']})")
                continue
            for it in items:
                head = it["headline"] or "(no headline)"
                if len(head) > 90:
                    head = head[:87] + "..."
                src = f" [{it['source']}]" if it["source"] else ""
                print(f"    - {head}{src}")
                if it["url"]:
                    print(f"      {it['url']}")
        print("\n  Headlines are raw facts for YOU to read and judge -- not a")
        print("  buy/sell signal. ETFs (e.g. GLD) usually have no company news.")

    print("\nNOTE: Flags and facts only. This tool does NOT place orders and does")
    print("NOT tell you to buy or sell. A stop-loss limits losses but does not")
    print("guarantee a fill at that exact price. You decide; you trade yourself.")
    print("Educational information, not investment advice.")


def main():
    p = argparse.ArgumentParser(description="Take-profit / stop-loss monitor + news")
    p.add_argument("--csv", required=True, help="path to broker positions CSV")
    p.add_argument("--take", type=float, default=3.0, help="take-profit %% (default 3)")
    p.add_argument("--stop", type=float, default=2.0, help="stop-loss %% (default 2)")
    p.add_argument("--anchor", choices=["cost", "current"], default="cost",
                   help="measure thresholds from original cost or today's price")
    p.add_argument("--news", action="store_true", help="also fetch Finnhub news sentiment")
    p.add_argument("--finnhub-key", default=os.environ.get("FINNHUB_KEY"),
                   help="Finnhub API key (or set FINNHUB_KEY env var)")
    args = p.parse_args()
    monitor(args.csv, take=args.take, stop=args.stop, anchor=args.anchor,
            use_news=args.news, finnhub_key=args.finnhub_key)


if __name__ == "__main__":
    main()
