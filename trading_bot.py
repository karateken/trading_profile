#!/usr/bin/env python3
"""
trading_bot.py  -  Multi-strategy educational backtester + daily-signal bot.

NEW IN THIS VERSION
-------------------
Four strategies you can run and COMPARE side by side, all through the same
honest backtest engine (realistic costs + in-sample / out-of-sample split):

  1. ma_crossover  - trend:  fast moving-average crosses above slow one
  2. momentum      - trend:  price is higher than it was N days ago
  3. rsi_reversion - mean-reversion: buy when oversold (RSI low), exit at neutral
  4. bollinger     - breakout: buy when price breaks above upper band

The point of having several is to SEE that no single strategy wins everywhere:
trend strategies do well in trending markets and bleed in choppy ones;
mean-reversion does the opposite. Most still struggle to beat buy-and-hold
after costs. That comparison is the whole lesson.

This is a learning tool. No leverage, no real money, NOT investment advice.

Examples:
    python trading_bot.py --ticker XEQT.TO          # compare ALL strategies
    python trading_bot.py --ticker SPY --strategy momentum
    python trading_bot.py --ticker AAPL --optimize  # tune ma_crossover (read the warning!)
"""

import argparse
import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    from fundamentals import show_fundamentals
except ImportError:
    show_fundamentals = None

try:
    from trends import show_trends
except ImportError:
    show_trends = None

TRADING_DAYS = 252


# --------------------------------------------------------------------------- #
# 1. DATA
# --------------------------------------------------------------------------- #
def load_data(ticker, start, end):
    # Prefer the shared data_source layer (lets cloud use stooq instead of yfinance)
    try:
        from data_source import daily_history
        df = daily_history(ticker, start=start)
        if df is not None and not df.empty:
            if end:
                df = df[df.index <= pd.to_datetime(end)]
            return df.dropna()
    except ImportError:
        pass
    # Fallback: direct yfinance
    if yf is None:
        raise SystemExit("Please `pip install yfinance` to fetch real data.")
    df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if df.empty:
        raise SystemExit(f"No data returned for {ticker}. Check the symbol.")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[["Close"]].rename(columns={"Close": "close"}).dropna()


# --------------------------------------------------------------------------- #
# 2. SHARED HELPERS
# --------------------------------------------------------------------------- #
def _rsi(close, period):
    """Relative Strength Index (0-100). Low = oversold, high = overbought."""
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _state_position(entry, exit_):
    """
    Turn entry/exit *events* into a held position (1) or flat (0).
    Used by strategies where you hold until an exit condition fires,
    rather than re-deciding every single day.
    """
    pos = np.zeros(len(entry))
    holding = 0
    e, x = entry.fillna(False).values, exit_.fillna(False).values
    for i in range(len(pos)):
        if holding == 0 and e[i]:
            holding = 1
        elif holding == 1 and x[i]:
            holding = 0
        pos[i] = holding
    return pd.Series(pos, index=entry.index)


# --------------------------------------------------------------------------- #
# 3. STRATEGIES
#    Each returns a "raw" signal: the position you'd WANT as of today's close
#    (1 = hold the asset, 0 = cash). The backtest engine shifts it by one day
#    so you only ever trade on information you actually had.
# --------------------------------------------------------------------------- #
def strat_ma_crossover(df, fast=20, slow=100):
    f = df["close"].rolling(fast).mean()
    s = df["close"].rolling(slow).mean()
    return (f > s).astype(int)


def strat_momentum(df, lookback=90):
    return (df["close"] > df["close"].shift(lookback)).astype(int)


def strat_rsi_reversion(df, period=14, oversold=30, exit_level=50):
    rsi = _rsi(df["close"], period)
    return _state_position(rsi < oversold, rsi > exit_level)


def strat_bollinger(df, period=20, k=2.0):
    mid = df["close"].rolling(period).mean()
    sd = df["close"].rolling(period).std()
    upper = mid + k * sd
    return _state_position(df["close"] > upper, df["close"] < mid)


STRATEGIES = {
    "ma_crossover":  (strat_ma_crossover,  dict(fast=20, slow=100)),
    "momentum":      (strat_momentum,      dict(lookback=90)),
    "rsi_reversion": (strat_rsi_reversion, dict(period=14, oversold=30, exit_level=50)),
    "bollinger":     (strat_bollinger,     dict(period=20, k=2.0)),
}


def build_signal(df, name, **params):
    fn = STRATEGIES[name][0]
    out = df.copy()
    out["raw_pos"] = fn(out, **params).astype(float)
    out["position"] = out["raw_pos"].shift(1).fillna(0)  # trade on yesterday's signal
    return out.dropna()


# --------------------------------------------------------------------------- #
# 4. BACKTEST ENGINE  (shared by every strategy, so comparisons are fair)
# --------------------------------------------------------------------------- #
def backtest(df, slippage_bps=5.0):
    df = df.copy()
    df["mkt_ret"] = df["close"].pct_change().fillna(0)
    df["strat_ret"] = df["position"] * df["mkt_ret"]
    df["trade"] = df["position"].diff().abs().fillna(0)
    df["cost"] = df["trade"] * (slippage_bps / 10_000.0)
    df["strat_ret"] = df["strat_ret"] - df["cost"]
    df["strat_equity"] = (1 + df["strat_ret"]).cumprod()
    df["mkt_equity"] = (1 + df["mkt_ret"]).cumprod()
    return df


def metrics(returns, equity):
    n = len(returns)
    if n == 0 or equity.iloc[-1] <= 0:
        return dict(CAGR=float("nan"), Sharpe=float("nan"),
                    MaxDD=float("nan"), Total=float("nan"))
    years = n / TRADING_DAYS
    cagr = equity.iloc[-1] ** (1 / years) - 1
    sharpe = (returns.mean() / returns.std() * np.sqrt(TRADING_DAYS)
              if returns.std() > 0 else 0.0)
    max_dd = (equity / equity.cummax() - 1).min()
    return dict(CAGR=cagr, Sharpe=sharpe, MaxDD=max_dd, Total=equity.iloc[-1] - 1)


def _row(name, m, trades=None):
    s = (f"  {name:<16} CAGR {m['CAGR']*100:6.2f}%  Sharpe {m['Sharpe']:5.2f}  "
         f"MaxDD {m['MaxDD']*100:6.1f}%  Total {m['Total']*100:7.1f}%")
    if trades is not None:
        s += f"  Trades {trades}"
    print(s)


# --------------------------------------------------------------------------- #
# 5. COMPARE ALL STRATEGIES  (in-sample vs out-of-sample)
# --------------------------------------------------------------------------- #
def compare(df, split=0.7, slippage_bps=5.0, only=None):
    names = [only] if only else list(STRATEGIES.keys())
    cut = int(len(df) * split)
    for period_name, lo, hi in [("IN-SAMPLE (tuned on)", 0, cut),
                                 ("OUT-OF-SAMPLE (the real test)", cut, len(df))]:
        print(f"\n=== {period_name} ===")
        bh_printed = False
        for name in names:
            params = STRATEGIES[name][1]
            sig = build_signal(df, name, **params)
            part = sig.loc[df.index[lo]:df.index[min(hi, len(df)) - 1]]
            bt = backtest(part, slippage_bps)
            m = metrics(bt["strat_ret"], bt["strat_equity"])
            _row(name, m, int(bt["trade"].sum()))
            if not bh_printed:
                _row("buy_and_hold", metrics(bt["mkt_ret"], bt["mkt_equity"]))
                bh_printed = True


# --------------------------------------------------------------------------- #
# 6. OPTIMIZER (ma_crossover only) — with the usual loud warning
# --------------------------------------------------------------------------- #
def optimize(df, split, slippage_bps):
    cut = int(len(df) * split)
    in_dates = df.index[:cut]
    best, best_sharpe = None, -np.inf
    for fast in range(5, 60, 5):
        for slow in range(50, 250, 25):
            if fast >= slow:
                continue
            sig = build_signal(df, "ma_crossover", fast=fast, slow=slow)
            in_s = sig.loc[in_dates[0]:in_dates[-1]]
            if len(in_s) < 50:
                continue
            bt = backtest(in_s, slippage_bps)
            m = metrics(bt["strat_ret"], bt["strat_equity"])
            if m["Sharpe"] > best_sharpe:
                best_sharpe, best = m["Sharpe"], (fast, slow)
    print(f"\nBest in-sample ma_crossover: fast={best[0]}, slow={best[1]} "
          f"(Sharpe={best_sharpe:.2f})")
    print(">>> Watch the OUT-OF-SAMPLE number below. The gap is the lesson. <<<")
    STRATEGIES["ma_crossover"] = (strat_ma_crossover,
                                  dict(fast=best[0], slow=best[1]))
    compare(df, split, slippage_bps, only="ma_crossover")


# --------------------------------------------------------------------------- #
# 7. DAILY REVIEW: what does EACH strategy say today?
# --------------------------------------------------------------------------- #
def daily_review(df):
    print("\n--- DAILY REVIEW (signal as of last close) ---")
    print(f"Date: {df.index[-1].date()}   Close: {df['close'].iloc[-1]:.2f}\n")
    for name in STRATEGIES:
        params = STRATEGIES[name][1]
        sig = build_signal(df, name, **params)
        now = sig["raw_pos"].iloc[-1]
        prev = sig["raw_pos"].iloc[-2] if len(sig) > 1 else now
        call = "IN  (hold/buy)" if now == 1 else "OUT (cash)"
        flip = "  <-- flipped today!" if prev != now else ""
        print(f"  {name:<16} {call}{flip}")
    print("\n(Paper signals for learning only - do not place real orders from this.)")


# --------------------------------------------------------------------------- #
def main():
    p = argparse.ArgumentParser(description="Multi-strategy educational backtester")
    p.add_argument("--ticker", default="SPY")
    p.add_argument("--start", default="2010-01-01")
    p.add_argument("--end", default=None)
    p.add_argument("--strategy", choices=list(STRATEGIES.keys()), default=None,
                   help="run one strategy; omit to compare all")
    p.add_argument("--split", type=float, default=0.7)
    p.add_argument("--slippage_bps", type=float, default=5.0)
    p.add_argument("--optimize", action="store_true")
    p.add_argument("--fundamentals", action="store_true",
                   help="also show company fundamentals (neutral, no buy/sell)")
    p.add_argument("--trends", action="store_true",
                   help="also show multi-year revenue/earnings/FCF trends (neutral)")
    args = p.parse_args()

    df = load_data(args.ticker, args.start, args.end)
    print(f"Loaded {len(df)} days of {args.ticker} "
          f"({df.index[0].date()} -> {df.index[-1].date()})")

    if args.optimize:
        optimize(df, args.split, args.slippage_bps)
    else:
        compare(df, args.split, args.slippage_bps, only=args.strategy)

    daily_review(df)

    if args.fundamentals:
        if show_fundamentals is None:
            print("\n(fundamentals.py not found - put it in the same folder.)")
        else:
            show_fundamentals(args.ticker)

    if args.trends:
        if show_trends is None:
            print("\n(trends.py not found - put it in the same folder.)")
        else:
            show_trends(args.ticker)


if __name__ == "__main__":
    main()
