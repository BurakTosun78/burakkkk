import pandas as pd


def ema(s: pd.Series, period: int) -> pd.Series:
    return s.ewm(span=period, adjust=False, min_periods=period).mean()


def _wilder(s: pd.Series, period: int) -> pd.Series:
    return s.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    d = close.diff()
    gain = _wilder(d.clip(lower=0), period)
    loss = _wilder(-d.clip(upper=0), period)
    out = 100 - 100 / (1 + gain / loss)
    return out.where(loss != 0, 100.0).where(gain.notna())


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev = close.shift()
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return _wilder(tr, period)
