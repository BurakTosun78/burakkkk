from dataclasses import dataclass

import pandas as pd

from .config import Config
from .engine import SimAccount, Trade
from .strategy import add_signals


@dataclass
class Result:
    trades: list[Trade]
    equity: pd.Series  # her mum kapanışında kasa
    initial: float

    def stats(self) -> dict:
        pnls = [t.pnl for t in self.trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        final = float(self.equity.iloc[-1]) if len(self.equity) else self.initial
        dd = (self.equity / self.equity.cummax() - 1).min() if len(self.equity) else 0.0
        days = max((self.equity.index[-1] - self.equity.index[0]).days, 1) if len(self.equity) else 1
        growth = max(final / self.initial, 1e-9)
        return {
            "işlem sayısı": len(pnls),
            "kazanma oranı %": round(100 * len(wins) / len(pnls), 1) if pnls else 0.0,
            "toplam getiri %": round(100 * (final / self.initial - 1), 2),
            "yıllık getiri %": round(100 * (growth ** (365 / days) - 1), 2),
            "günlük ort. getiri %": round(100 * (growth ** (1 / days) - 1), 4),
            "maks. düşüş %": round(100 * float(dd), 2),
            "profit factor": round(sum(wins) / -sum(losses), 2) if sum(losses) < 0 else float("inf"),
            "ort. işlem (USDT)": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
            "son kasa (USDT)": round(final, 2),
        }


def run_backtest(df: pd.DataFrame, cfg: Config) -> Result:
    """Sinyal i. mumun kapanışında oluşur, işlem i+1. mumun açılışında yapılır.

    Fonlama (funding) ücretleri hesaba katılmaz.
    """
    df = add_signals(df, cfg.strategy).reset_index(drop=True)
    acc = SimAccount(cfg, cfg.paper.initial_balance)
    next_open = df["open"].shift(-1)
    equity = []
    for r, nxt in zip(df.itertuples(index=False), next_open):
        acc.on_bar(int(r.ts), r.open, r.high, r.low, int(r.signal), r.atr, None if pd.isna(nxt) else nxt)
        equity.append(acc.equity(r.close))
    if acc.position:
        last = df.iloc[-1]
        acc.close(last.close, int(last.ts), "end")
        equity[-1] = acc.balance
    return Result(acc.trades, pd.Series(equity, index=pd.to_datetime(df["ts"], unit="ms")), cfg.paper.initial_balance)
