#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
data_source.py - one place to fetch price data, swappable for cloud vs local.

Why this exists
---------------
- Local (your PC): yfinance works fine.
- Cloud (GitHub Actions): yfinance's requests often get rate-limited/blocked
  by Yahoo from datacenter IPs. stooq.com serves free daily CSV with no key
  and is reliable from cloud runners.
- Finnhub free tier gives reliable real-time /quote but NOT historical candles
  (those moved to paid), so we use Finnhub only for the latest price if a key
  is set, and stooq/yfinance for the historical series the strategies need.

Choose source with env var DATA_SOURCE = "yfinance" (default) or "stooq".
Optional FINNHUB_KEY env var enables a precise real-time last price.

Public functions:
  daily_history(symbol, start="2018-01-01") -> DataFrame[index=date, col 'close']
  latest_price(symbol) -> float | None
"""

import io
import os
import urllib.request
from datetime import datetime

import pandas as pd

SOURCE = os.environ.get("DATA_SOURCE", "yfinance").lower()
FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")


# ---------- historical daily series ----------
def _history_yfinance(symbol, start):
    import yfinance as yf
    df = yf.download(symbol, start=start, auto_adjust=True, progress=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[["Close"]].rename(columns={"Close": "close"}).dropna()


def _stooq_symbol(symbol):
    """stooq uses e.g. 'aapl.us' for US stocks, 'xeqt.ca'? (TSX uses .us-style?)."""
    s = symbol.lower()
    if s.endswith(".to"):           # Toronto -> stooq uses .ca? actually .to maps weirdly
        return s.replace(".to", ".ca")
    if "." in s:
        return s                    # already has a suffix
    return s + ".us"                # default to US listing


def _history_stooq(symbol, start):
    sym = _stooq_symbol(symbol)
    url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=15).read().decode()
    if not raw or raw.startswith("<") or "Date" not in raw:
        return None
    df = pd.read_csv(io.StringIO(raw))
    if "Date" not in df.columns or "Close" not in df.columns:
        return None
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")[["Close"]].rename(columns={"Close": "close"})
    df = df[df.index >= pd.to_datetime(start)].dropna()
    return df if not df.empty else None


def daily_history(symbol, start="2018-01-01"):
    """Return DataFrame indexed by date with a single 'close' column, or None."""
    try:
        if SOURCE == "stooq":
            df = _history_stooq(symbol, start)
            if df is None:                       # fallback if stooq misses a symbol
                df = _history_yfinance(symbol, start)
        else:
            df = _history_yfinance(symbol, start)
        return df
    except Exception:
        return None


# ---------- latest price ----------
def _finnhub_quote(symbol):
    if not FINNHUB_KEY:
        return None
    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
    try:
        raw = urllib.request.urlopen(url, timeout=10).read().decode()
        import json
        c = json.loads(raw).get("c")
        return float(c) if c else None
    except Exception:
        return None


def latest_price(symbol):
    """Finnhub real-time quote if key set; else last close from history."""
    p = _finnhub_quote(symbol)
    if p:
        return p
    hist = daily_history(symbol, start="2024-01-01")
    if hist is not None and not hist.empty:
        return float(hist["close"].iloc[-1])
    return None
