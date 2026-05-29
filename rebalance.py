import os
import json
import time
import math
import eth_account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

def get_precision_data(info):
    """Récupère les décimales (szDecimals) pour chaque token."""
    meta = info.spot_meta()
    precision = {}
    for token in meta["tokens"]:
        precision[token["name"]] = token["szDecimals"]
    return precision

def get_spot_prices(info):
    meta = info.spot_meta()
    contexts = info.spot_asset_contexts()
    prices = {}
    universe = meta["universe"]
    asset_contexts = contexts[1]
    for i, pair in enumerate(universe):
        coin = pair["name"].split("/")[0]
        prices[coin] = float(asset_contexts[i]["midPx"])
    return prices

def truncate_float(n, decimals):
    if decimals == 0:
        return math.floor(n)
    factor = 10 ** decimals
    return math.floor(n * factor) / factor

def main():
    if not os.path.exists("config.json"):
        print("config.json manquant. Lancez init_config.py d'abord.")
        return

    config = load_config()
    secret_key = os.getenv("HYPERLIQUID_SECRET_KEY")
    address = os.getenv("HYPERLIQUID_ADDRESS")

    if not secret_key or not address:
        print("Erreur: Secrets non configurés.")
        return

    account = eth_account.Account.from_key(secret_key)
    info = Info(constants.MAINNET_API_URL, skip_ws=True)
    exchange = Exchange(account, constants.MAINNET_API_URL)

    # Données de marché
    prices = get_spot_prices(info)
    precision_map = get_precision_data(info)
    user_state = info.spot_user_state(address)
    balances = {b["coin"]: float(b["total"]) for b in user_state["balances"]}

    print(f"--- Rebalance Session: {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
    
    global_cfg = config["global"]
    tokens_cfg = config["tokens"]

    for coin, cfg in tokens_cfg.items():
        if not cfg.get("enabled", True):
            continue

        price = prices.get(coin)
        if not price:
            continue

        balance = balances.get(coin, 0.0)
        current_value = balance * price
        
        target = cfg.get("target_value_usd", global_cfg["default_target_value_usd"])
        threshold = cfg.get("rebalance_threshold_pct", global_cfg["default_rebalance_threshold_pct"])
        trade_size_usd = cfg.get("trade_size_usd", global_cfg["default_trade_size_usd"])
        min_order_usd = global_cfg.get("min_order_usd", 11.0)

        upper_bound = target * (1 + threshold)
        lower_bound = target * (1 - threshold)

        print(f"[{coin}] Valeur: ${current_value:.2f} | Cible: ${target} | Range: [${lower_bound:.1f} - ${upper_bound:.1f}]")

        action = None
        if current_value > upper_bound:
            action = "SELL"
        elif current_value < lower_bound:
            action = "BUY"

        if action:
            # Vérification de la taille minimale
            actual_trade_usd = max(trade_size_usd, min_order_usd)
            sz = actual_trade_usd / price
            
            # Ajustement aux décimales autorisées par Hyperliquid
            decimals = precision_map.get(coin, 0)
            sz_truncated = truncate_float(sz, decimals)
            
            if sz_truncated == 0:
                print(f"  ! Taille d'ordre trop petite après troncature ({sz} -> 0)")
                continue

            print(f"  -> Action: {action} {sz_truncated} {coin} (~${sz_truncated * price:.2f})")
            
            try:
                is_buy = (action == "BUY")
                # Sur Hyperliquid spot, on utilise market_open ou order avec un prix agressif
                # market_open(name, is_buy, sz, px, slippage)
                # Pour spot, le nom est "COIN/USDC"
                res = exchange.market_open(f"{coin}/USDC", is_buy, sz_truncated, None, 0.01)
                print(f"  Résultat: {res}")
                # Rate limit protection (simple sleep entre les ordres)
                time.sleep(1) 
            except Exception as e:
                print(f"  Erreur: {e}")

if __name__ == "__main__":
    main()
