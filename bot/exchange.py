import os
import time

import ccxt
import pandas as pd

COLUMNS = ["ts", "open", "high", "low", "close", "volume"]


def make_exchange(mode: str = "paper"):
    """paper: anahtarsız, yalnızca piyasa verisi. demo: Binance demo hesabı. live: gerçek hesap."""
    params = {"enableRateLimit": True, "options": {"defaultType": "future"}}
    if mode in ("demo", "live"):
        key, secret = os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_API_SECRET")
        if not key or not secret:
            raise SystemExit(".env içinde BINANCE_API_KEY ve BINANCE_API_SECRET gerekli (.env.example'a bakın)")
        params |= {"apiKey": key, "secret": secret}
    ex = ccxt.binanceusdm(params)
    if mode == "demo":
        ex.enable_demo_trading(True)
    return ex


def timeframe_ms(tf: str) -> int:
    return ccxt.Exchange.parse_timeframe(tf) * 1000


def to_frame(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=COLUMNS)


def closed_candles(ex, symbol: str, tf: str, limit: int = 300) -> pd.DataFrame:
    """Son `limit` mum; henüz kapanmamış olan son mum atılır."""
    df = to_frame(ex.fetch_ohlcv(symbol, tf, limit=limit))
    now = ex.milliseconds()
    return df[df["ts"] + timeframe_ms(tf) <= now].reset_index(drop=True)


def fetch_history(ex, symbol: str, tf: str, days: int) -> pd.DataFrame:
    """Son `days` günün kapanmış mumlarını sayfa sayfa indirir."""
    step = timeframe_ms(tf)
    now = ex.milliseconds()
    since = now - days * 86_400_000
    rows = []
    while since < now:
        batch = ex.fetch_ohlcv(symbol, tf, since=since, limit=1000)
        if not batch:
            break
        rows += batch
        since = batch[-1][0] + step
        time.sleep(ex.rateLimit / 1000)
    df = to_frame(rows).drop_duplicates("ts").sort_values("ts")
    return df[df["ts"] + step <= now].reset_index(drop=True)
