"""EMA kesişimi + RSI filtresi. Sinyal yalnızca KAPANMIŞ mumdan üretilir."""
import pandas as pd

from .config import Strategy
from .indicators import atr, ema, rsi


def add_signals(df: pd.DataFrame, s: Strategy) -> pd.DataFrame:
    """df sütunları: ts, open, high, low, close, volume. signal: 1 long, -1 short, 0 yok."""
    df = df.copy()
    df["ema_fast"] = ema(df["close"], s.ema_fast)
    df["ema_slow"] = ema(df["close"], s.ema_slow)
    df["rsi"] = rsi(df["close"], s.rsi_period)
    df["atr"] = atr(df["high"], df["low"], df["close"], s.atr_period)

    diff = df["ema_fast"] - df["ema_slow"]
    prev = diff.shift()
    up = (prev <= 0) & (diff > 0) & (df["rsi"] < s.rsi_long_max)
    down = (prev >= 0) & (diff < 0) & (df["rsi"] > s.rsi_short_min)
    df["signal"] = 0
    df.loc[up, "signal"] = 1
    df.loc[down, "signal"] = -1
    return df
