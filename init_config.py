import os
import json
from hyperliquid.info import Info
from hyperliquid.utils import constants

def init_config(address):
    info = Info(constants.MAINNET_API_URL, skip_ws=True)
    print(f"Récupération des positions pour {address}...")
    
    try:
        user_state = info.spot_user_state(address)
        balances = user_state.get("balances", [])
        
        config = {
            "global": {
                "default_target_value_usd": 100.0,
                "default_rebalance_threshold_pct": 0.5,
                "default_trade_size_usd": 12.0,
                "min_order_usd": 11.0, # Buffer de sécurité au-dessus de 10$
                "cooldown_minutes": 7
            },
            "tokens": {}
        }
        
        for b in balances:
            coin = b["coin"]
            if coin == "USDC":
                continue
            
            # Configuration par défaut par token
            config["tokens"][coin] = {
                "enabled": True,
                "target_value_usd": 100.0,
                "rebalance_threshold_pct": 0.5,
                "trade_size_usd": 12.0
            }
            
        with open("config.json", "w") as f:
            json.dump(config, f, indent=4)
            
        print(f"Fichier config.json généré avec {len(config['tokens'])} tokens.")
        
    except Exception as e:
        print(f"Erreur lors de l'initialisation: {e}")

if __name__ == "__main__":
    import sys
    addr = sys.argv[1] if len(sys.argv) > 1 else os.getenv("HYPERLIQUID_ADDRESS")
    if addr:
        init_config(addr)
    else:
        print("Veuillez fournir une adresse (argument ou variable d'env HYPERLIQUID_ADDRESS)")
