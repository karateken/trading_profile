#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_report.py - run the daily checks and write a phone-friendly HTML report.

Part A: your current portfolio (watchlist TP/SL, snapshot, two-step screen)
Part B: your AI satellite watchlist (5 holdings you monitor)
Part C: swing-trading scan universe (larger candidate pool, screen only)

Signals only, not orders. Educational, not investment advice.
"""

import argparse
import io
import os
import re
import sys
from contextlib import redirect_stdout
from datetime import datetime
from html import escape

import watchlist as wl
import portfolio as pf
import screener as sc


def capture(fn, *args, **kwargs):
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            fn(*args, **kwargs)
    except SystemExit as e:
        buf.write(f"\n(stopped: {e})")
    except Exception as e:
        buf.write(f"\n(error: {e})")
    return buf.getvalue()


def colorize(text):
    t = escape(text)
    rules = [
        (r"(TAKE-PROFIT reached[^\n<]*)", "tp"),
        (r"(STOP-LOSS reached[^\n<]*)", "sl"),
        (r"(&gt;&gt;&gt; Good co \+ uptrend)", "good"),
        (r"(Good co, WAIT[^\n<]*)", "wait"),
        (r"(!!! Weak co RISING[^\n<]*)", "trap"),
        (r"\b(IN )", "in"),
        (r"\b(OUT)\b", "out"),
        (r"\[(PASS)\]", "pass"),
        (r"\[(FAIL)\]", "fail"),
        (r"(within range)", "range"),
    ]
    for pat, cls in rules:
        t = re.sub(pat, rf'<span class="{cls}">\1</span>', t)
    return t


GUIDE_HTML = """
<div class="guide">
  <h2>點睇呢份報告（中文導讀）</h2>
  <p>呢份係「提示」報告，<b>唔係買賣指令</b>。所有決定同落單由你自己做。核心 ETF（例如 XEQT）長線揸住，唔喺度擇時。</p>
  <ul>
    <li><b>IN</b> = 該技術策略而家會「持倉」（趨勢向上）</li>
    <li><b>OUT</b> = 該技術策略而家會「揸現金」（趨勢未向上）</li>
    <li><b>TAKE-PROFIT reached</b> = 升到你設嘅止賺位 → 考慮減持</li>
    <li><b>STOP-LOSS reached</b> = 跌到你設嘅止蝕位 → 考慮離場</li>
  </ul>
  <p>兩步篩選四個格：<b>Good co + uptrend</b>（考慮入場）、<b>Good co, WAIT</b>（等時機）、<b>Weak co RISING</b>（陷阱）、<b>Skip / ETF</b>。</p>
  <p class="warn">Part C 係 swing 掃描池（只篩選、唔代表持有）。掃描多 ≠ 買得多；揀邊隻、買唔買、止蝕，全部係你嘅決定。訊號唔等於保證。教學資訊，唔係投資建議。</p>
</div>
"""

CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, "PingFang HK", "Microsoft JhengHei", sans-serif;
  margin: 0; padding: 12px; background: #f4f5f7; color: #1a1a1a; line-height: 1.6; }
h1 { font-size: 20px; margin: 8px 0 4px; }
h2 { font-size: 16px; margin: 0 0 8px; }
.stamp { color: #666; font-size: 13px; margin-bottom: 12px; }
.guide { background: #eef3fb; border-radius: 12px; padding: 14px 16px; margin-bottom: 16px; font-size: 14px; }
.guide ul { margin: 6px 0; padding-left: 20px; }
.guide .warn { color: #8a4b00; margin-top: 8px; }
.card { background: #fff; border-radius: 12px; padding: 14px 16px; margin-bottom: 14px;
  box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.card h2 { border-bottom: 1px solid #eee; padding-bottom: 6px; }
pre { white-space: pre-wrap; word-wrap: break-word; font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 12.5px; margin: 8px 0; overflow-x: auto; }
.tp, .good, .in, .pass { color: #0a7d3c; font-weight: 600; }
.sl, .trap, .fail { color: #c0271a; font-weight: 600; }
.wait, .range { color: #8a6d00; font-weight: 600; }
.out { color: #777; }
.foot { color: #888; font-size: 12px; text-align: center; margin: 16px 0; }
"""


def section(title, body_text):
    return f'<div class="card"><h2>{escape(title)}</h2><pre>{colorize(body_text)}</pre></div>'


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True)
    p.add_argument("--satellite", default=None)
    p.add_argument("--universe", default=None)
    p.add_argument("--take", type=float, default=3.0)
    p.add_argument("--stop", type=float, default=2.0)
    p.add_argument("--minpass", type=int, default=3)
    p.add_argument("--finnhub-key", default=None)
    args = p.parse_args()

    use_news = bool(args.finnhub_key)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    parts = []

    parts.append('<h1>每日股票報告</h1>')
    parts.append(f'<div class="stamp">{stamp}</div>')
    parts.append(GUIDE_HTML)

    # PART A - current portfolio
    parts.append('<h1>Part A：你嘅現有組合</h1>')
    parts.append(section("A1 · 止賺 / 止蝕檢查",
        capture(wl.monitor, args.csv, take=args.take, stop=args.stop,
                anchor="current", use_news=use_news, finnhub_key=args.finnhub_key)))
    parts.append(section("A2 · 組合快照（已記錄歷史）",
        capture(pf.monitor, args.csv, show_signals=False, logfile="portfolio_history.csv")))
    parts.append(section("A3 · 兩步篩選（基本面＋技術）",
        capture(sc.run, sc.read_tickers_from_csv(args.csv), min_pass=args.minpass)))

    # PART B - satellite monitoring (5 holdings)
    if args.satellite and os.path.exists(args.satellite):
        parts.append('<h1>Part B：AI 衛星監察（持有/長線）</h1>')
        parts.append(section("B1 · 衛星 止賺 / 止蝕檢查",
            capture(wl.monitor, args.satellite, take=args.take, stop=args.stop,
                    anchor="current", use_news=use_news, finnhub_key=args.finnhub_key)))
        parts.append(section("B2 · 衛星 兩步篩選",
            capture(sc.run, sc.read_tickers_from_csv(args.satellite), min_pass=args.minpass)))
    elif args.satellite:
        parts.append(f'<div class="card"><p>注意：搵唔到 {escape(args.satellite)}，已略過衛星部分。</p></div>')

    # PART C - swing scan universe (screen only, larger pool)
    if args.universe and os.path.exists(args.universe):
        parts.append('<h1>Part C：Swing 掃描池（只篩選，唔代表持有）</h1>')
        parts.append(section("C1 · 掃描池 兩步篩選（搵 Good co + uptrend 做候選）",
            capture(sc.run, sc.read_tickers_from_csv(args.universe), min_pass=args.minpass)))
    elif args.universe:
        parts.append(f'<div class="card"><p>注意：搵唔到 {escape(args.universe)}，已略過掃描池部分。</p></div>')

    parts.append('<div class="foot">訊號只供參考，唔係買賣指令。決定同落單係你做。<br>Educational, not investment advice.</div>')

    html = (f'<!DOCTYPE html><html lang="zh-HK"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>每日股票報告 {stamp}</title><style>{CSS}</style></head>'
            f'<body>{"".join(parts)}</body></html>')

    out = f"daily_report_{datetime.now().strftime('%Y-%m-%d')}.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML report written: {out}")


if __name__ == "__main__":
    main()
