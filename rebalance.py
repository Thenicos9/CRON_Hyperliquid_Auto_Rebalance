"""Bot de rebalancing automatique du portefeuille Spot Hyperliquid.

Le bot lit une configuration de cibles par token (`config.json`) et, à chaque
exécution, ramène chaque position vers sa valeur cible en USD :
- vend le surplus si la valeur dépasse la bande haute,
- rachète si la valeur passe sous la bande basse.

Conçu pour tourner en CRON (GitHub Actions ou serveur). Voir le README.

Fonctions principalement « pures » (decide_action, truncate_float,
cooldown_active, order_result_status, validate_config…) pour faciliter les tests.
"""

import os
import sys
import json
import time
import math
import argparse
import logging
import urllib.request
import urllib.error
from typing import Any, Optional

import eth_account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

CONFIG_PATH = "config.json"
STATE_PATH = "rebalance_state.json"

logger = logging.getLogger("rebalance")


# --------------------------------------------------------------------------- #
# Validation des entrées
# --------------------------------------------------------------------------- #
def is_valid_eth_address(address: Any) -> bool:
    """Retourne True si `address` ressemble à une adresse Ethereum (0x + 40 hex)."""
    if not isinstance(address, str):
        return False
    if not address.startswith("0x") or len(address) != 42:
        return False
    return all(c in "0123456789abcdefABCDEF" for c in address[2:])


def validate_env(secret_key: Optional[str], address: Optional[str], *, require_key: bool) -> None:
    """Valide les variables d'environnement sensibles.

    Args:
        secret_key: clé privée / clé d'agent Hyperliquid (peut être None en dry-run).
        address: adresse publique du compte.
        require_key: si True, l'absence de clé est une erreur (mode live).

    Raises:
        ValueError: si une valeur est manquante ou mal formée.
    """
    if not address:
        raise ValueError("HYPERLIQUID_ADDRESS non défini.")
    if not is_valid_eth_address(address):
        raise ValueError(f"HYPERLIQUID_ADDRESS invalide (attendu 0x + 40 hex): {address!r}")
    if require_key:
        if not secret_key:
            raise ValueError("HYPERLIQUID_SECRET_KEY non défini.")
        # Une clé privée eth est 32 octets => 0x + 64 hex (66) ou 64 sans préfixe.
        key_body = secret_key[2:] if secret_key.startswith("0x") else secret_key
        if len(key_body) != 64 or not all(c in "0123456789abcdefABCDEF" for c in key_body):
            raise ValueError("HYPERLIQUID_SECRET_KEY mal formée (attendu 32 octets hex).")


def _check_number(value: Any, name: str, *, low: float, high: Optional[float], inclusive_low: bool = False) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} doit être un nombre, reçu {value!r}.")
    if inclusive_low:
        if value < low:
            raise ValueError(f"{name} doit être >= {low}, reçu {value}.")
    else:
        if value <= low:
            raise ValueError(f"{name} doit être > {low}, reçu {value}.")
    if high is not None and value > high:
        raise ValueError(f"{name} doit être <= {high}, reçu {value}.")


def validate_config(config: dict[str, Any]) -> None:
    """Valide la structure et les plages de `config.json`.

    Raises:
        ValueError: à la première incohérence rencontrée.
    """
    if not isinstance(config, dict):
        raise ValueError("config.json doit contenir un objet JSON.")
    if "global" not in config or not isinstance(config["global"], dict):
        raise ValueError("Section 'global' manquante ou invalide.")
    if "tokens" not in config or not isinstance(config["tokens"], dict):
        raise ValueError("Section 'tokens' manquante ou invalide.")

    g = config["global"]
    _check_number(g.get("default_target_value_usd"), "global.default_target_value_usd", low=0, high=None)
    _check_number(g.get("default_rebalance_threshold_pct"), "global.default_rebalance_threshold_pct", low=0, high=1)
    _check_number(g.get("default_trade_size_usd"), "global.default_trade_size_usd", low=0, high=None)
    _check_number(g.get("min_order_usd", 11.0), "global.min_order_usd", low=0, high=None)
    _check_number(g.get("cooldown_minutes", 0), "global.cooldown_minutes", low=0, high=None, inclusive_low=True)
    _check_number(g.get("default_slippage_pct", 0.01), "global.default_slippage_pct", low=0, high=1)

    for coin, cfg in config["tokens"].items():
        if not isinstance(cfg, dict):
            raise ValueError(f"tokens.{coin} doit être un objet.")
        _check_number(cfg.get("target_value_usd", g["default_target_value_usd"]),
                      f"tokens.{coin}.target_value_usd", low=0, high=None)
        _check_number(cfg.get("rebalance_threshold_pct", g["default_rebalance_threshold_pct"]),
                      f"tokens.{coin}.rebalance_threshold_pct", low=0, high=1)
        _check_number(cfg.get("trade_size_usd", g["default_trade_size_usd"]),
                      f"tokens.{coin}.trade_size_usd", low=0, high=None)


def load_config(path: str = CONFIG_PATH) -> dict[str, Any]:
    """Charge et valide la configuration depuis le disque."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"{path} introuvable. Lancez d'abord init_config.py.")
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} n'est pas un JSON valide: {e}")
    validate_config(config)
    return config


# --------------------------------------------------------------------------- #
# État persistant (cooldown)
# --------------------------------------------------------------------------- #
def load_state(path: str = STATE_PATH) -> dict[str, Any]:
    """Charge l'état persistant (timestamps des derniers trades). Tolérant aux erreurs."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {"last_trade": {}}


def save_state(state: dict[str, Any], path: str = STATE_PATH) -> None:
    """Persiste l'état sur le disque (best-effort)."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except OSError as e:
        logger.warning("Impossible d'écrire l'état (%s): %s", path, e)


def cooldown_active(last_ts_ms: Optional[float], cooldown_minutes: float, now_ms: float) -> bool:
    """Retourne True si un trade a eu lieu depuis moins de `cooldown_minutes`."""
    if not last_ts_ms or cooldown_minutes <= 0:
        return False
    return (now_ms - last_ts_ms) < cooldown_minutes * 60_000


# --------------------------------------------------------------------------- #
# Données de marché (avec cache du spot_meta)
# --------------------------------------------------------------------------- #
def get_precision_data(meta: dict[str, Any]) -> dict[str, int]:
    """Mappe chaque token vers son nombre de décimales autorisées (szDecimals)."""
    return {token["name"]: token["szDecimals"] for token in meta["tokens"]}


def get_spot_prices(info: Info, meta: dict[str, Any]) -> dict[str, float]:
    """Récupère le prix mid de chaque coin spot (clé = nom du coin de base)."""
    contexts = info.spot_asset_contexts()
    asset_contexts = contexts[1]
    prices: dict[str, float] = {}
    for i, pair in enumerate(meta["universe"]):
        coin = pair["name"].split("/")[0]
        prices[coin] = float(asset_contexts[i]["midPx"])
    return prices


# --------------------------------------------------------------------------- #
# Calculs (purs)
# --------------------------------------------------------------------------- #
def truncate_float(n: float, decimals: int) -> float:
    """Tronque (vers le bas) `n` au nombre de décimales donné."""
    if decimals <= 0:
        return float(math.floor(n))
    factor = 10 ** decimals
    return math.floor(n * factor) / factor


def decide_action(current_value: float, target: float, threshold: float) -> Optional[str]:
    """Décide de l'action de rebalancing pour une position.

    Returns:
        "SELL" si la valeur dépasse la bande haute, "BUY" si sous la bande basse,
        sinon None (dans la bande, rien à faire).
    """
    upper_bound = target * (1 + threshold)
    lower_bound = target * (1 - threshold)
    if current_value > upper_bound:
        return "SELL"
    if current_value < lower_bound:
        return "BUY"
    return None


def order_result_status(res: Any) -> tuple[bool, str]:
    """Interprète la réponse d'un ordre Hyperliquid.

    Hyperliquid renvoie souvent {"status":"ok", ...} même quand un ordre
    individuel échoue (l'erreur est nichée dans response.data.statuses).
    Cette fonction renvoie (succès, détail lisible).
    """
    if not isinstance(res, dict):
        return False, str(res)
    if res.get("status") != "ok":
        return False, str(res)
    try:
        statuses = res["response"]["data"]["statuses"]
    except (KeyError, TypeError):
        return False, str(res)

    ok = True
    messages: list[str] = []
    for st in statuses:
        if not isinstance(st, dict):
            messages.append(str(st))
            continue
        if "error" in st:
            ok = False
            messages.append(f"error: {st['error']}")
        elif "filled" in st:
            f = st["filled"]
            messages.append(f"filled {f.get('totalSz')} @ {f.get('avgPx')}")
        elif "resting" in st:
            messages.append("resting (non rempli immédiatement)")
        else:
            messages.append(str(st))
    return ok, "; ".join(messages) if messages else str(res)


# --------------------------------------------------------------------------- #
# Notifications (best-effort, sans dépendance externe)
# --------------------------------------------------------------------------- #
def _http_post(url: str, payload: dict[str, Any], timeout: float = 10.0) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=timeout).read()


def notify(message: str) -> None:
    """Envoie une notification via Telegram et/ou Discord si configurés.

    Variables d'environnement reconnues :
        TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
        DISCORD_WEBHOOK_URL
    Les erreurs d'envoi sont logguées mais n'interrompent jamais le bot.
    """
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID")
    discord_url = os.getenv("DISCORD_WEBHOOK_URL")

    if tg_token and tg_chat:
        try:
            _http_post(
                f"https://api.telegram.org/bot{tg_token}/sendMessage",
                {"chat_id": tg_chat, "text": message},
            )
        except (urllib.error.URLError, OSError) as e:
            logger.warning("Notification Telegram échouée: %s", e)

    if discord_url:
        try:
            _http_post(discord_url, {"content": message})
        except (urllib.error.URLError, OSError) as e:
            logger.warning("Notification Discord échouée: %s", e)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_rebalance(
    config: dict[str, Any],
    info: Info,
    exchange: Optional[Exchange],
    address: str,
    state: dict[str, Any],
    *,
    dry_run: bool,
    now_ms: Optional[float] = None,
) -> list[str]:
    """Exécute une passe de rebalancing sur tous les tokens activés.

    Args:
        exchange: None en dry-run (aucun ordre n'est envoyé).
    Returns:
        Liste de lignes de log destinées aux notifications (résumé des actions/erreurs).
    """
    if now_ms is None:
        now_ms = time.time() * 1000

    meta = info.spot_meta()
    prices = get_spot_prices(info, meta)
    precision_map = get_precision_data(meta)
    user_state = info.spot_user_state(address)
    balances = {b["coin"]: float(b["total"]) for b in user_state["balances"]}
    usdc_available = balances.get("USDC", 0.0)

    global_cfg = config["global"]
    tokens_cfg = config["tokens"]
    min_order_usd = global_cfg.get("min_order_usd", 11.0)
    cooldown_minutes = global_cfg.get("cooldown_minutes", 0)
    slippage = global_cfg.get("default_slippage_pct", 0.01)
    last_trade = state.setdefault("last_trade", {})

    mode = "DRY-RUN" if dry_run else "LIVE"
    logger.info("--- Rebalance (%s) %s ---", mode, time.strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("Solde USDC disponible: $%.2f", usdc_available)

    summary: list[str] = []

    for coin, cfg in tokens_cfg.items():
        if not cfg.get("enabled", True):
            continue

        price = prices.get(coin)
        if price is None or price <= 0:
            logger.info("[%s] Prix indisponible, ignoré.", coin)
            continue

        balance = balances.get(coin, 0.0)
        current_value = balance * price
        target = cfg.get("target_value_usd", global_cfg["default_target_value_usd"])
        threshold = cfg.get("rebalance_threshold_pct", global_cfg["default_rebalance_threshold_pct"])
        trade_size_usd = cfg.get("trade_size_usd", global_cfg["default_trade_size_usd"])

        lower = target * (1 - threshold)
        upper = target * (1 + threshold)
        logger.info("[%s] Valeur: $%.2f | Cible: $%.2f | Bande: [$%.1f - $%.1f]",
                    coin, current_value, target, lower, upper)

        action = decide_action(current_value, target, threshold)
        if action is None:
            continue

        # Anti-rebond : ne pas retrader le même coin trop vite.
        if cooldown_active(last_trade.get(coin), cooldown_minutes, now_ms):
            logger.info("  ⏳ [%s] En cooldown, action %s reportée.", coin, action)
            continue

        actual_trade_usd = max(trade_size_usd, min_order_usd)
        sz = actual_trade_usd / price
        decimals = precision_map.get(coin, 0)
        sz_truncated = truncate_float(sz, decimals)

        if sz_truncated <= 0:
            logger.info("  ! [%s] Taille trop petite après troncature (%.10f -> 0).", coin, sz)
            continue

        order_usd = sz_truncated * price
        is_buy = action == "BUY"

        # Vérification de solde AVANT de tenter l'ordre.
        if is_buy and order_usd > usdc_available:
            msg = f"[{coin}] BUY ${order_usd:.2f} ignoré: USDC insuffisant (dispo ${usdc_available:.2f})."
            logger.warning("  ! %s", msg)
            summary.append("⚠️ " + msg)
            continue
        if not is_buy and sz_truncated > balance:
            msg = f"[{coin}] SELL {sz_truncated} ignoré: solde insuffisant (dispo {balance})."
            logger.warning("  ! %s", msg)
            summary.append("⚠️ " + msg)
            continue

        logger.info("  -> %s %s %s (~$%.2f)", action, sz_truncated, coin, order_usd)

        if dry_run:
            summary.append(f"🧪 [DRY-RUN] {action} {sz_truncated} {coin} (~${order_usd:.2f})")
            continue

        assert exchange is not None  # garanti en mode live
        try:
            res = exchange.market_open(f"{coin}/USDC", is_buy, sz_truncated, None, slippage)
        except Exception as e:  # noqa: BLE001 - on veut survivre à toute erreur réseau/SDK
            msg = f"[{coin}] {action} a levé une exception: {e}"
            logger.error("  ✗ %s", msg)
            summary.append("❌ " + msg)
            continue

        ok, detail = order_result_status(res)
        if ok:
            # Met à jour le solde USDC local et le cooldown.
            usdc_available += order_usd if not is_buy else -order_usd
            last_trade[coin] = now_ms
            msg = f"[{coin}] {action} OK: {detail}"
            logger.info("  ✓ %s", msg)
            summary.append("✅ " + msg)
        else:
            msg = f"[{coin}] {action} ÉCHEC: {detail}"
            logger.error("  ✗ %s", msg)
            summary.append("❌ " + msg)

        # Protection rate-limit basique entre deux ordres.
        time.sleep(1)

    return summary


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Bot de rebalancing Spot Hyperliquid.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simule sans envoyer d'ordre (clé privée non requise).")
    parser.add_argument("--config", default=CONFIG_PATH, help="Chemin vers config.json.")
    parser.add_argument("--state", default=STATE_PATH, help="Chemin vers le fichier d'état (cooldown).")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        logger.error("Configuration invalide: %s", e)
        return 1

    secret_key = os.getenv("HYPERLIQUID_SECRET_KEY")
    address = os.getenv("HYPERLIQUID_ADDRESS")
    try:
        validate_env(secret_key, address, require_key=not args.dry_run)
    except ValueError as e:
        logger.error("Environnement invalide: %s", e)
        return 1

    info = Info(constants.MAINNET_API_URL, skip_ws=True)
    exchange: Optional[Exchange] = None
    if not args.dry_run:
        account = eth_account.Account.from_key(secret_key)
        exchange = Exchange(account, constants.MAINNET_API_URL)

    state = load_state(args.state)

    try:
        summary = run_rebalance(config, info, exchange, address, state, dry_run=args.dry_run)
    except Exception as e:  # noqa: BLE001 - dernier filet de sécurité + notification
        logger.exception("Erreur fatale pendant le rebalancing.")
        notify(f"🚨 Rebalance Hyperliquid: erreur fatale: {e}")
        return 1

    if not args.dry_run:
        save_state(state, args.state)
        # Ne notifie que s'il s'est passé quelque chose de notable.
        if summary:
            notify("Rebalance Hyperliquid:\n" + "\n".join(summary))

    return 0


if __name__ == "__main__":
    sys.exit(main())
