import json

import numpy as np
import pandas as pd
import pytest

from bot.backtest import run_backtest
from bot.config import Config, load_config
from bot.engine import SimAccount
from bot.indicators import atr, ema, rsi
from bot.live import LiveBroker
from bot.risk import position_size
from bot.runner import step_paper
from bot.strategy import add_signals

H = 3_600_000


def candles(closes, spread=0.5):
    c = np.asarray(closes, dtype=float)
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"ts": np.arange(len(c)) * H, "open": o, "high": np.maximum(o, c) + spread,
                         "low": np.minimum(o, c) - spread, "close": c, "volume": 1.0})


def wave(n=3000, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return candles(1000 + 60 * np.sin(t / 40) + np.cumsum(rng.normal(0, 1, n)) + rng.normal(0, 6, n), spread=3)


def test_indicators():
    s = pd.Series(np.arange(1, 101, dtype=float))
    assert ema(s, 10).iloc[-1] == pytest.approx(95.5, abs=0.01)  # doğrusal seride gecikme (N-1)/2
    assert rsi(s, 14).iloc[-1] == 100
    assert rsi(pd.Series(np.arange(100, 0, -1.0)), 14).iloc[-1] == pytest.approx(0)
    df = candles([100] * 50, spread=1)
    assert atr(df.high, df.low, df.close, 14).iloc[-1] == pytest.approx(2)


def test_signals_fire_on_cross_only():
    df = add_signals(wave(), Config().strategy)
    diff = df.ema_fast - df.ema_slow
    sig = df[df.signal != 0]
    assert len(sig) > 10 and {1, -1} == set(sig.signal)
    assert (np.sign(diff[sig.index]) == sig.signal).all()  # sinyal yönü = kesişim yönü
    assert (np.sign(diff.shift()[sig.index]) == -sig.signal).all()  # bir önceki mumda ters taraftaydı
    assert ((sig.signal == 1) & (sig.rsi >= 70)).sum() == 0


def test_position_size():
    cfg = Config()
    # risk %1 x 1000 = 10 USDT; stop mesafesi 2 x 5 = 10 -> 1 adet
    assert position_size(1000, 1000, 5, cfg) == pytest.approx(1.0)
    # kaldıraç tavanı: 3 x 1000 / 1000 = 3 adet
    assert position_size(1000, 1000, 0.1, cfg) == pytest.approx(3.0)
    # stop likidasyona çok yakın -> işlem yok
    assert position_size(1000, 1000, 150, cfg) == 0
    assert position_size(1000, 1000, float("nan"), cfg) == 0


def no_cost_cfg():
    cfg = Config()
    cfg.costs.taker_fee = cfg.costs.slippage = 0
    return cfg


def test_stop_loss_costs_one_percent():
    acc = SimAccount(no_cost_cfg(), 1000)
    acc.on_bar(0, 100, 101, 99, 1, 2.0, 100)  # long @100, SL 96, TP 106
    assert (acc.position.sl, acc.position.tp) == (96, 106)
    acc.on_bar(H, 100, 107, 95, 0, 2.0, 100)  # ikisi de değdi -> SL sayılır
    assert acc.position is None and acc.trades[0].reason == "sl"
    assert acc.balance == pytest.approx(990)


def test_take_profit_gap_and_flip():
    acc = SimAccount(no_cost_cfg(), 1000)
    acc.on_bar(0, 100, 101, 99, -1, 2.0, 100)  # short @100, SL 104, TP 94
    acc.on_bar(H, 100, 101, 93, 0, 2.0, 95)
    assert acc.trades[0].reason == "tp" and acc.balance == pytest.approx(1015)
    acc.on_bar(2 * H, 100, 101, 99, -1, 2.0, 100)
    acc.on_bar(3 * H, 110, 111, 109, 0, 2.0, 110)  # stopun ötesinde açılış: 110'dan dolar
    assert acc.trades[1].exit == 110
    acc.on_bar(4 * H, 100, 101, 99, 1, 2.0, 100)
    acc.on_bar(5 * H, 100, 101, 99, -1, 2.0, 99)  # ters sinyal: kapat ve short aç
    assert acc.trades[2].reason == "flip" and acc.position.side == -1


def test_no_take_profit_and_long_only():
    cfg = no_cost_cfg()
    cfg.strategy.tp_atr, cfg.strategy.allow_short = 0, False
    acc = SimAccount(cfg, 1000)
    assert acc.on_bar(0, 100, 101, 99, -1, 2.0, 100) == [] and acc.position is None  # short açılmaz
    acc.on_bar(H, 100, 101, 99, 1, 2.0, 100)
    assert acc.position.tp is None
    acc.on_bar(2 * H, 100, 500, 99, 0, 2.0, 500)  # kâr al yok: pozisyon taşınır
    assert acc.position is not None
    acc = SimAccount.from_dict(cfg, json.loads(json.dumps(acc.to_dict())))
    acc.on_bar(3 * H, 500, 501, 499, -1, 2.0, 500)  # ters sinyal: kapat, short açma
    assert acc.position is None and acc.trades[0].reason == "flip" and acc.balance > 1000


def test_fees_reduce_balance_and_daily_halt():
    cfg = Config()
    acc = SimAccount(cfg, 1000)
    acc.on_bar(0, 100, 101, 99, 1, 2.0, 100)
    acc.on_bar(H, 100, 100.5, 99.5, 0, 2.0, None)
    t = acc.close(acc.position.entry, H, "end")
    assert t.pnl < 0 and acc.balance == pytest.approx(1000 + t.pnl)
    acc.balance = acc.day_start_balance * 0.94
    assert "limit" in acc.on_bar(2 * H, 100, 101, 99, 1, 2.0, 100)[0] and acc.position is None
    acc.on_bar(24 * H, 100, 101, 99, 1, 2.0, 100)  # yeni gün: limit sıfırlanır
    assert acc.position is not None


def test_backtest_accounting():
    cfg = Config()
    res = run_backtest(wave(), cfg)
    assert len(res.trades) > 10
    assert res.equity.iloc[-1] == pytest.approx(cfg.paper.initial_balance + sum(t.pnl for t in res.trades))
    assert {t.reason for t in res.trades} <= {"sl", "tp", "flip", "end"}
    assert res.stats()["maks. düşüş %"] <= 0


def test_backtest_has_no_lookahead():
    """Geleceği değiştirmek, geçmişteki işlemleri değiştirmemeli."""
    cfg, df = Config(), wave()
    cut = 2000
    df2 = df.copy()
    df2.loc[cut:, ["open", "high", "low", "close"]] *= 1.5
    a = [t for t in run_backtest(df, cfg).trades if t.exit_ts < (cut - 1) * H]
    b = [t for t in run_backtest(df2, cfg).trades if t.exit_ts < (cut - 1) * H]
    assert a and a == b


def test_paper_step_matches_backtest_and_state_roundtrip():
    cfg, df = Config(), wave(600)
    acc, last = SimAccount(cfg, cfg.paper.initial_balance), 0
    for i in range(cfg.strategy.ema_slow + 2, len(df) + 1):
        last = step_paper(acc, last, df.iloc[:i], cfg)
        acc = SimAccount.from_dict(cfg, json.loads(json.dumps(acc.to_dict())))
        assert step_paper(acc, last, df.iloc[:i], cfg) == last  # aynı mum iki kez işlenmez
    assert len(acc.trades) >= 3
    # paper: mum kapanışından girer; backtest: sonraki açılıştan. Bu veride ikisi eşit.
    bt = run_backtest(df, cfg).trades
    for p, b in zip(acc.trades, bt):
        assert (p.side, p.entry_ts, p.reason) == (b.side, b.entry_ts, b.reason)
        assert p.pnl == pytest.approx(b.pnl)


def test_config_validation(tmp_path):
    assert load_config("config.yaml").mode == "paper"
    p = tmp_path / "c.yaml"
    p.write_text("risk:\n  leverage: 50\n")
    with pytest.raises(ValueError):
        load_config(p)
    p.write_text("strategy:\n  ema_fats: 5\n")
    with pytest.raises(ValueError):
        load_config(p)


class FakeExchange:
    def __init__(self, pos=None, fail_stops=False):
        self.pos, self.fail_stops, self.orders, self.cancels = pos, fail_stops, [], 0

    def milliseconds(self): return 5 * H
    def fetch_balance(self): return {"USDT": {"total": 1000.0}}
    def fetch_ticker(self, s): return {"last": 1000.0}
    def market(self, s): return {"limits": {"amount": {"min": 0.001}, "cost": {"min": 5}}}
    def amount_to_precision(self, s, q): return f"{q:.3f}"
    def price_to_precision(self, s, p): return f"{p:.1f}"
    def cancel_all_orders(self, s, params=None): self.cancels += 1

    def fetch_positions(self, syms):
        return [{"side": "long" if self.pos[0] == 1 else "short", "contracts": self.pos[1]}] if self.pos else []

    def create_order(self, sym, type_, side, qty, price=None, params=None):
        params = params or {}
        if self.fail_stops and "stopLossPrice" in params:
            raise RuntimeError("reddedildi")
        self.orders.append((side, qty, params))
        if not params:
            self.pos = (1 if side == "buy" else -1, qty)
        elif set(params) == {"reduceOnly"}:
            self.pos = None
        return {"average": 1000.0}


def test_live_entry_places_sl_and_tp(tmp_path):
    ex = FakeExchange()
    LiveBroker(ex, Config(), tmp_path / "s.json").on_signal(1, 5.0)
    assert ex.orders == [
        ("buy", 1.0, {}),
        ("sell", 1.0, {"stopLossPrice": "990.0", "reduceOnly": True}),
        ("sell", 1.0, {"takeProfitPrice": "1015.0", "reduceOnly": True}),
    ]


def test_live_flip_hold_and_failed_stop(tmp_path):
    ex = FakeExchange(pos=(1, 2.0))
    b = LiveBroker(ex, Config(), tmp_path / "s.json")
    b.on_signal(1, 5.0)  # aynı yön: dokunma
    b.on_signal(0, 5.0)
    assert ex.orders == []
    b.on_signal(-1, 5.0)  # ters: kapat, short aç
    assert ex.orders[0] == ("sell", 2.0, {"reduceOnly": True})
    assert ex.orders[1] == ("sell", 1.0, {}) and ex.pos == (-1, 1.0)
    assert ex.orders[2][2]["stopLossPrice"] == "1010.0" and ex.orders[3][2]["takeProfitPrice"] == "985.0"

    ex = FakeExchange(fail_stops=True)
    with pytest.raises(RuntimeError):
        LiveBroker(ex, Config(), tmp_path / "s2.json").on_signal(1, 5.0)
    assert ex.pos is None  # stopsuz pozisyon bırakılmadı


def test_live_no_tp_and_long_only(tmp_path):
    cfg = Config()
    cfg.strategy.tp_atr, cfg.strategy.allow_short = 0, False
    ex = FakeExchange()
    b = LiveBroker(ex, cfg, tmp_path / "s.json")
    b.on_signal(-1, 5.0)
    assert ex.orders == []
    b.on_signal(1, 5.0)
    assert [set(o[2]) for o in ex.orders] == [set(), {"stopLossPrice", "reduceOnly"}]
    b.on_signal(-1, 5.0)  # long kapanır, short açılmaz
    assert ex.pos is None and len(ex.orders) == 3


def test_live_daily_halt_and_min_size(tmp_path):
    ex = FakeExchange()
    b = LiveBroker(ex, Config(), tmp_path / "s.json")
    assert not b.halted(1000)
    assert b.halted(940)
    ex.fetch_balance = lambda: {"USDT": {"total": 940.0}}
    b.on_signal(1, 5.0)
    assert ex.orders == []
    ex2 = FakeExchange()
    ex2.fetch_balance = lambda: {"USDT": {"total": 0.5}}
    LiveBroker(ex2, Config(), tmp_path / "s3.json").on_signal(1, 5.0)
    assert ex2.orders == []
