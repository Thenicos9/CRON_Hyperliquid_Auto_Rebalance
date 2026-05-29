"""Tests unitaires des fonctions pures et de l'orchestration du bot."""

import pytest

import rebalance as rb


# --------------------------- truncate_float --------------------------- #
@pytest.mark.parametrize("n,decimals,expected", [
    (1.23456, 2, 1.23),
    (1.999, 0, 1.0),
    (0.00009, 4, 0.0),
    (10.5, 0, 10.0),
    (5.6789, 3, 5.678),
])
def test_truncate_float(n, decimals, expected):
    assert rb.truncate_float(n, decimals) == expected


def test_truncate_float_negative_decimals():
    assert rb.truncate_float(12.9, -1) == 12.0


# --------------------------- decide_action --------------------------- #
def test_decide_action_sell_above_band():
    assert rb.decide_action(160, 100, 0.5) == "SELL"


def test_decide_action_buy_below_band():
    assert rb.decide_action(40, 100, 0.5) == "BUY"


def test_decide_action_inside_band_noop():
    assert rb.decide_action(120, 100, 0.5) is None
    assert rb.decide_action(150, 100, 0.5) is None  # bord supérieur exact: pas d'action
    assert rb.decide_action(50, 100, 0.5) is None   # bord inférieur exact: pas d'action


# --------------------------- cooldown_active --------------------------- #
def test_cooldown_active_recent_trade():
    now = 1_000_000
    last = now - 5 * 60_000  # il y a 5 min
    assert rb.cooldown_active(last, 7, now) is True


def test_cooldown_expired():
    now = 1_000_000
    last = now - 10 * 60_000  # il y a 10 min
    assert rb.cooldown_active(last, 7, now) is False


def test_cooldown_none_or_zero():
    assert rb.cooldown_active(None, 7, 1000) is False
    assert rb.cooldown_active(500, 0, 1000) is False


# --------------------------- is_valid_eth_address --------------------------- #
@pytest.mark.parametrize("addr,valid", [
    ("0x" + "a" * 40, True),
    ("0x" + "A" * 40, True),
    ("0x" + "g" * 40, False),   # caractère non-hex
    ("0x" + "a" * 39, False),   # trop court
    ("a" * 42, False),          # pas de préfixe 0x
    (None, False),
    (12345, False),
])
def test_is_valid_eth_address(addr, valid):
    assert rb.is_valid_eth_address(addr) is valid


# --------------------------- validate_env --------------------------- #
def test_validate_env_dry_run_no_key_ok():
    rb.validate_env(None, "0x" + "a" * 40, require_key=False)  # ne lève pas


def test_validate_env_requires_key_in_live():
    with pytest.raises(ValueError):
        rb.validate_env(None, "0x" + "a" * 40, require_key=True)


def test_validate_env_bad_address():
    with pytest.raises(ValueError):
        rb.validate_env("0x" + "b" * 64, "not-an-address", require_key=True)


def test_validate_env_good_key():
    rb.validate_env("0x" + "b" * 64, "0x" + "a" * 40, require_key=True)


def test_validate_env_bad_key_length():
    with pytest.raises(ValueError):
        rb.validate_env("0x" + "b" * 10, "0x" + "a" * 40, require_key=True)


# --------------------------- validate_config --------------------------- #
def _good_config():
    return {
        "global": {
            "default_target_value_usd": 100.0,
            "default_rebalance_threshold_pct": 0.1,
            "default_trade_size_usd": 12.0,
            "min_order_usd": 11.0,
            "cooldown_minutes": 7,
            "default_slippage_pct": 0.01,
        },
        "tokens": {"PURR": {"enabled": True}},
    }


def test_validate_config_ok():
    rb.validate_config(_good_config())


def test_validate_config_threshold_out_of_range():
    cfg = _good_config()
    cfg["global"]["default_rebalance_threshold_pct"] = 1.5
    with pytest.raises(ValueError):
        rb.validate_config(cfg)


def test_validate_config_negative_target():
    cfg = _good_config()
    cfg["global"]["default_target_value_usd"] = -5
    with pytest.raises(ValueError):
        rb.validate_config(cfg)


def test_validate_config_missing_section():
    with pytest.raises(ValueError):
        rb.validate_config({"global": {}})


def test_validate_config_per_token_override_invalid():
    cfg = _good_config()
    cfg["tokens"]["PURR"]["rebalance_threshold_pct"] = 2.0
    with pytest.raises(ValueError):
        rb.validate_config(cfg)


# --------------------------- order_result_status --------------------------- #
def test_order_result_filled():
    res = {"status": "ok", "response": {"data": {"statuses": [
        {"filled": {"totalSz": "1.5", "avgPx": "10.0"}}]}}}
    ok, detail = rb.order_result_status(res)
    assert ok is True
    assert "filled" in detail


def test_order_result_nested_error():
    res = {"status": "ok", "response": {"data": {"statuses": [
        {"error": "Insufficient margin"}]}}}
    ok, detail = rb.order_result_status(res)
    assert ok is False
    assert "Insufficient margin" in detail


def test_order_result_top_level_error():
    ok, detail = rb.order_result_status({"status": "err", "response": "boom"})
    assert ok is False


def test_order_result_non_dict():
    ok, _ = rb.order_result_status("oops")
    assert ok is False


# --------------------------- state load/save --------------------------- #
def test_state_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    rb.save_state({"last_trade": {"PURR": 123}}, str(p))
    loaded = rb.load_state(str(p))
    assert loaded["last_trade"]["PURR"] == 123


def test_load_state_missing_returns_default(tmp_path):
    loaded = rb.load_state(str(tmp_path / "nope.json"))
    assert loaded == {"last_trade": {}}
