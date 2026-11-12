from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml


@dataclass
class Strategy:
    ema_fast: int = 20
    ema_slow: int = 50
    rsi_period: int = 14
    rsi_long_max: float = 70
    rsi_short_min: float = 30
    atr_period: int = 14
    sl_atr: float = 2.0
    tp_atr: float = 3.0


@dataclass
class Risk:
    risk_per_trade: float = 0.01
    leverage: int = 3
    max_daily_loss: float = 0.05


@dataclass
class Costs:
    taker_fee: float = 0.0005
    slippage: float = 0.0002


@dataclass
class Paper:
    initial_balance: float = 1000.0


@dataclass
class Config:
    mode: str = "paper"
    symbol: str = "BTC/USDT:USDT"
    timeframe: str = "1h"
    strategy: Strategy = field(default_factory=Strategy)
    risk: Risk = field(default_factory=Risk)
    costs: Costs = field(default_factory=Costs)
    paper: Paper = field(default_factory=Paper)

    def validate(self):
        s, r = self.strategy, self.risk
        if self.mode not in ("paper", "demo", "live"):
            raise ValueError(f"mode paper|demo|live olmalı: {self.mode!r}")
        if s.ema_fast >= s.ema_slow:
            raise ValueError("ema_fast, ema_slow'dan küçük olmalı")
        if not 0 < r.risk_per_trade <= 0.05:
            raise ValueError("risk_per_trade 0 ile 0.05 (%5) arasında olmalı")
        if not 1 <= r.leverage <= 20:
            raise ValueError("leverage 1 ile 20 arasında olmalı")
        if s.sl_atr <= 0 or s.tp_atr <= 0:
            raise ValueError("sl_atr ve tp_atr pozitif olmalı")
        return self


def _section(cls, data):
    data = data or {}
    unknown = set(data) - {f.name for f in fields(cls)}
    if unknown:
        raise ValueError(f"config: bilinmeyen alan(lar) {sorted(unknown)}")
    return cls(**data)


def load_config(path="config.yaml") -> Config:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    sections = {"strategy": Strategy, "risk": Risk, "costs": Costs, "paper": Paper}
    kwargs = {k: (_section(sections[k], v) if k in sections else v) for k, v in raw.items()}
    return _section(Config, kwargs).validate()
