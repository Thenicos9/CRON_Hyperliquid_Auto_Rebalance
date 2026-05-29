import os
import json
import time
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
import eth_account

# Configuration par défaut
DEFAULT_CONFIG = {
    "target_value_usd": 100.0,
    "rebalance_threshold_pct": 0.5,  # 50%
    "trade_size_usd": 12.0,
    "assets": []  # Liste des assets à surveiller, ex: ["PURR", "HYPE"]
}

def load_config():
    config_path = "config.json"
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return DEFAULT_CONFIG

def get_spot_prices(info):
    """Récupère les prix médians de tous les actifs spot."""
    meta = info.spot_meta()
    contexts = info.spot_asset_contexts()
    
    prices = {}
    # Le format de contexts est [meta, [asset_contexts]]
    asset_contexts = contexts[1]
    for i, token_meta in enumerate(meta["tokens"]):
        # On cherche l'index dans l'univers pour trouver le prix
        # Note: L'index dans asset_contexts correspond à l'index dans l'univers
        pass # On va simplifier en utilisant midPx du context

    # Plus simple: mapper par nom via l'univers
    universe = meta["universe"]
    for i, pair in enumerate(universe):
        prices[pair["name"].split("/")[0]] = float(asset_contexts[i]["midPx"])
    
    return prices

def main():
    config = load_config()
    secret_key = os.getenv("HYPERLIQUID_SECRET_KEY")
    account_address = os.getenv("HYPERLIQUID_ADDRESS")

    if not secret_key or not account_address:
        print("Erreur: HYPERLIQUID_SECRET_KEY ou HYPERLIQUID_ADDRESS non configuré.")
        return

    account = eth_account.Account.from_key(secret_key)
    info = Info(constants.MAINNET_API_URL, skip_ws=True)
    exchange = Exchange(account, constants.MAINNET_API_URL)

    print(f"Démarrage du rebalancement pour le compte: {account_address}")
    
    # 1. Récupérer les soldes spot
    user_state = info.spot_user_state(account_address)
    balances = {b["coin"]: float(b["total"]) for b in user_state["balances"]}
    
    # 2. Récupérer les prix
    prices = get_spot_prices(info)
    
    # Si aucun asset n'est spécifié dans la config, on prend tous ceux qu'on possède (sauf USDC)
    assets_to_watch = config["assets"] if config["assets"] else [c for c in balances.keys() if c != "USDC"]

    for coin in assets_to_watch:
        if coin not in prices:
            print(f"Prix non trouvé pour {coin}, passage...")
            continue
            
        balance = balances.get(coin, 0.0)
        price = prices[coin]
        current_value = balance * price
        
        target = config["target_value_usd"]
        threshold = config["rebalance_threshold_pct"]
        trade_size = config["trade_size_usd"]
        
        upper_bound = target * (1 + threshold)
        lower_bound = target * (1 - threshold)
        
        print(f"Asset: {coin} | Valeur actuelle: ${current_value:.2f} | Cible: ${target}")

        if current_value > upper_bound:
            # Trop de valeur -> Vendre
            amount_to_sell = trade_size / price
            print(f"Action: Vente de {amount_to_sell:.4f} {coin} (${trade_size})")
            try:
                # Ordre au marché (on utilise un prix glissant pour simuler market ou un prix très bas pour sell)
                # Sur Hyperliquid spot, 'True' pour buy, 'False' pour sell
                # Pour un market sell, on met un prix très bas
                result = exchange.market_open(f"{coin}/USDC", False, amount_to_sell, None, 0.01)
                print(f"Résultat: {result}")
            except Exception as e:
                print(f"Erreur lors de la vente: {e}")
                
        elif current_value < lower_bound:
            # Pas assez de valeur -> Acheter
            amount_to_buy = trade_size / price
            print(f"Action: Achat de {amount_to_buy:.4f} {coin} (${trade_size})")
            try:
                # Pour un market buy, on met un prix très haut
                result = exchange.market_open(f"{coin}/USDC", True, amount_to_buy, None, 0.01)
                print(f"Résultat: {result}")
            except Exception as e:
                print(f"Erreur lors de l'achat: {e}")
        else:
            print(f"Statut: OK (dans la fourchette ${lower_bound} - ${upper_bound})")

if __name__ == "__main__":
    main()
