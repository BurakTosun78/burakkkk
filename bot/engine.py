"""Simüle hesap: backtest ve paper modunun ortak işlem motoru."""
from dataclasses import asdict, dataclass, field

from .config import Config
from .risk import position_size, stop_prices


@dataclass
class Position:
    side: int  # 1 long, -1 short
    qty: float
    entry: float
    sl: float
    tp: float | None  # None: sabit kâr al yok, ters sinyalle çıkılır
    entry_ts: int


@dataclass
class Trade:
    side: int
    qty: float
    entry: float
    exit: float
    entry_ts: int
    exit_ts: int
    pnl: float  # komisyonlar düşülmüş net
    reason: str  # sl | tp | flip | end


@dataclass
class SimAccount:
    cfg: Config
    balance: float
    position: Position | None = None
    trades: list[Trade] = field(default_factory=list)
    day: int = -1
    day_start_balance: float = 0.0
    _entry_fee: float = 0.0

    def equity(self, price: float) -> float:
        p = self.position
        return self.balance + (p.side * p.qty * (price - p.entry) if p else 0.0)

    def halted(self) -> bool:
        """Günlük zarar limiti aşıldı mı?"""
        return self.balance <= self.day_start_balance * (1 - self.cfg.risk.max_daily_loss)

    def _open(self, side: int, price: float, atr: float, ts: int) -> None:
        fill = price * (1 + side * self.cfg.costs.slippage)
        qty = position_size(self.balance, fill, atr, self.cfg)
        if qty <= 0:
            return
        sl, tp = stop_prices(side, fill, atr, self.cfg)
        self._entry_fee = qty * fill * self.cfg.costs.taker_fee
        self.balance -= self._entry_fee
        self.position = Position(side, qty, fill, sl, tp, ts)

    def close(self, price: float, ts: int, reason: str) -> Trade:
        p = self.position
        fill = price * (1 - p.side * self.cfg.costs.slippage)
        fee = p.qty * fill * self.cfg.costs.taker_fee
        gross = p.side * p.qty * (fill - p.entry)
        self.balance += gross - fee
        t = Trade(p.side, p.qty, p.entry, fill, p.entry_ts, ts, gross - fee - self._entry_fee, reason)
        self.trades.append(t)
        self.position = None
        return t

    def on_bar(self, ts, open_, high, low, signal, atr, next_price) -> list[str]:
        """Kapanmış bir mumu işle.

        1) Açık pozisyonun SL/TP'si mum içinde tetiklendi mi? (ikisi de değdiyse SL sayılır)
        2) Mumun sinyaline göre next_price'tan (sonraki mumun açılışı) işlem yap.
        Olan olayların listesini döndürür.
        """
        events = []
        day = ts // 86_400_000
        if day != self.day:
            self.day, self.day_start_balance = day, self.balance

        p = self.position
        if p:
            hit_sl = low <= p.sl if p.side == 1 else high >= p.sl
            hit_tp = p.tp is not None and (high >= p.tp if p.side == 1 else low <= p.tp)
            if hit_sl:
                # Mum stopun ötesinde açıldıysa (gap) açılış fiyatından dolar.
                px = min(p.sl, open_) if p.side == 1 else max(p.sl, open_)
                events.append(f"SL {self.close(px, ts, 'sl').pnl:+.2f}")
            elif hit_tp:
                events.append(f"TP {self.close(p.tp, ts, 'tp').pnl:+.2f}")

        if next_price is None or not signal:
            return events
        if self.position and self.position.side == -signal:
            events.append(f"TERS SİNYAL kapat {self.close(next_price, ts, 'flip').pnl:+.2f}")
        if not self.position and (signal == 1 or self.cfg.strategy.allow_short):
            if self.halted():
                events.append("günlük zarar limiti: yeni işlem yok")
            else:
                self._open(signal, next_price, atr, ts)
                p = self.position
                if p:
                    events.append(
                        f"{'LONG' if signal == 1 else 'SHORT'} {p.qty:.6f} @ {p.entry:.2f} "
                        f"SL {p.sl:.2f} TP {p.tp and round(p.tp, 2)}"
                    )
        return events

    # --- paper modu için durum kaydı ---
    def to_dict(self) -> dict:
        return {
            "balance": self.balance,
            "position": asdict(self.position) if self.position else None,
            "trades": [asdict(t) for t in self.trades],
            "day": self.day,
            "day_start_balance": self.day_start_balance,
            "entry_fee": self._entry_fee,
        }

    @classmethod
    def from_dict(cls, cfg: Config, d: dict) -> "SimAccount":
        return cls(
            cfg,
            d["balance"],
            Position(**d["position"]) if d["position"] else None,
            [Trade(**t) for t in d["trades"]],
            d["day"],
            d["day_start_balance"],
            d["entry_fee"],
        )
