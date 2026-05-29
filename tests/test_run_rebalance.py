"""Tests d'intégration de run_rebalance avec des doublures (fakes) d'API."""

import pytest

import rebalance as rb


class FakeInfo:
    """Doublure minimale de hyperliquid.info.Info."""

    def __init__(self, balances, mid_px=10.0, sz_decimals=2):
        self._balances = balances
        self._mid_px = mid_px
        self._sz_decimals = sz_decimals

    def spot_meta(self):
        return {
            "tokens": [{"name": "PURR", "szDecimals": self._sz_decimals},
                       {"name": "USDC", "szDecimals": 2}],
            "universe": [{"name": "PURR/USDC"}],
        }

    def spot_asset_contexts(self):
        return [{}, [{"midPx": str(self._mid_px)}]]

    def spot_user_state(self, address):
        return {"balances": [{"coin": c, "total": str(v)} for c, v in self._balances.items()]}


class FakeExchange:
    """Doublure d'Exchange qui enregistre les ordres et renvoie un succès."""

    def __init__(self, result=None):
        self.orders = []
        self._result = result or {
            "status": "ok",
            "response": {"data": {"statuses": [{"filled": {"totalSz": "1", "avgPx": "10.0"}}]}},
        }

    def market_open(self, name, is_buy, sz, px, slippage):
        self.orders.append((name, is_buy, sz, px, slippage))
        return self._result


def base_config(**global_overrides):
    g = {
        "default_target_value_usd": 100.0,
        "default_rebalance_threshold_pct": 0.1,
        "default_trade_size_usd": 12.0,
        "min_order_usd": 11.0,
        "cooldown_minutes": 7,
        "default_slippage_pct": 0.01,
    }
    g.update(global_overrides)
    return {"global": g, "tokens": {"PURR": {"enabled": True}}}


ADDR = "0x" + "a" * 40


def test_buy_when_below_band():
    # 1 PURR @ $10 = $10, cible $100 => très en dessous => BUY
    info = FakeInfo(balances={"PURR": 1.0, "USDC": 500.0})
    ex = FakeExchange()
    state = {"last_trade": {}}
    summary = rb.run_rebalance(base_config(), info, ex, ADDR, state, dry_run=False, now_ms=1_000_000)
    assert len(ex.orders) == 1
    name, is_buy, sz, px, slippage = ex.orders[0]
    assert name == "PURR/USDC" and is_buy is True
    assert state["last_trade"]["PURR"] == 1_000_000
    assert any("✅" in s for s in summary)


def test_sell_when_above_band():
    # 20 PURR @ $10 = $200, cible $100 => au-dessus => SELL
    info = FakeInfo(balances={"PURR": 20.0, "USDC": 500.0})
    ex = FakeExchange()
    summary = rb.run_rebalance(base_config(), info, ex, ADDR, {"last_trade": {}},
                               dry_run=False, now_ms=1_000_000)
    assert ex.orders[0][1] is False  # is_buy False => SELL


def test_no_action_inside_band():
    # 10 PURR @ $10 = $100 => pile sur la cible => aucune action
    info = FakeInfo(balances={"PURR": 10.0, "USDC": 500.0})
    ex = FakeExchange()
    summary = rb.run_rebalance(base_config(), info, ex, ADDR, {"last_trade": {}},
                               dry_run=False, now_ms=1_000_000)
    assert ex.orders == []
    assert summary == []


def test_cooldown_blocks_trade():
    info = FakeInfo(balances={"PURR": 1.0, "USDC": 500.0})
    ex = FakeExchange()
    # dernier trade il y a 2 min, cooldown 7 min => bloqué
    state = {"last_trade": {"PURR": 1_000_000 - 2 * 60_000}}
    rb.run_rebalance(base_config(), info, ex, ADDR, state, dry_run=False, now_ms=1_000_000)
    assert ex.orders == []


def test_insufficient_usdc_blocks_buy():
    info = FakeInfo(balances={"PURR": 1.0, "USDC": 5.0})  # pas assez pour un ordre ~$11
    ex = FakeExchange()
    summary = rb.run_rebalance(base_config(), info, ex, ADDR, {"last_trade": {}},
                               dry_run=False, now_ms=1_000_000)
    assert ex.orders == []
    assert any("USDC insuffisant" in s for s in summary)


def test_dry_run_sends_no_order():
    info = FakeInfo(balances={"PURR": 1.0, "USDC": 500.0})
    summary = rb.run_rebalance(base_config(), info, None, ADDR, {"last_trade": {}},
                               dry_run=True, now_ms=1_000_000)
    assert any("DRY-RUN" in s for s in summary)


def test_failed_order_reported_and_no_cooldown_set():
    info = FakeInfo(balances={"PURR": 1.0, "USDC": 500.0})
    ex = FakeExchange(result={"status": "ok", "response": {"data": {"statuses": [
        {"error": "Order would immediately match"}]}}})
    state = {"last_trade": {}}
    summary = rb.run_rebalance(base_config(), info, ex, ADDR, state, dry_run=False, now_ms=1_000_000)
    assert any("❌" in s for s in summary)
    assert "PURR" not in state["last_trade"]  # échec => pas de cooldown


def test_disabled_token_skipped():
    cfg = base_config()
    cfg["tokens"]["PURR"]["enabled"] = False
    info = FakeInfo(balances={"PURR": 1.0, "USDC": 500.0})
    ex = FakeExchange()
    rb.run_rebalance(cfg, info, ex, ADDR, {"last_trade": {}}, dry_run=False, now_ms=1_000_000)
    assert ex.orders == []
