"""Génère un `config.json` de base en scannant les soldes Spot d'un compte.

Usage:
    python init_config.py [ADRESSE]
    # ou via la variable d'environnement HYPERLIQUID_ADDRESS

Le fichier généré ne contient AUCUN secret : uniquement des cibles et seuils.
Il ne doit pas écraser un config.json existant sans confirmation (--force).
"""

import os
import sys
import json
import argparse
from typing import Any

from hyperliquid.info import Info
from hyperliquid.utils import constants

CONFIG_PATH = "config.json"

DEFAULT_GLOBAL: dict[str, Any] = {
    "default_target_value_usd": 100.0,
    "default_rebalance_threshold_pct": 0.1,  # bande de +/- 10% autour de la cible
    "default_trade_size_usd": 12.0,
    "min_order_usd": 11.0,        # buffer de sécurité au-dessus de la limite Hyperliquid (10$)
    "cooldown_minutes": 7,        # anti-rebond entre deux trades d'un même token
    "default_slippage_pct": 0.01  # 1% de slippage max sur les ordres au marché
}


def is_valid_eth_address(address: Any) -> bool:
    """Retourne True si `address` ressemble à une adresse Ethereum (0x + 40 hex)."""
    if not isinstance(address, str):
        return False
    if not address.startswith("0x") or len(address) != 42:
        return False
    return all(c in "0123456789abcdefABCDEF" for c in address[2:])


def build_config(balances: list[dict[str, Any]]) -> dict[str, Any]:
    """Construit la structure de configuration à partir des soldes du compte.

    Tous les tokens non-USDC détenus sont ajoutés avec les valeurs par défaut.
    """
    config: dict[str, Any] = {"global": dict(DEFAULT_GLOBAL), "tokens": {}}
    for b in balances:
        coin = b["coin"]
        if coin == "USDC":
            continue
        config["tokens"][coin] = {
            "enabled": True,
            "target_value_usd": DEFAULT_GLOBAL["default_target_value_usd"],
            "rebalance_threshold_pct": DEFAULT_GLOBAL["default_rebalance_threshold_pct"],
            "trade_size_usd": DEFAULT_GLOBAL["default_trade_size_usd"],
        }
    return config


def init_config(address: str, path: str = CONFIG_PATH, *, force: bool = False) -> dict[str, Any]:
    """Récupère les positions du compte et écrit `config.json`.

    Raises:
        ValueError: adresse invalide.
        FileExistsError: le fichier existe déjà et force=False.
    """
    if not is_valid_eth_address(address):
        raise ValueError(f"Adresse invalide (attendu 0x + 40 hex): {address!r}")
    if os.path.exists(path) and not force:
        raise FileExistsError(f"{path} existe déjà. Utilisez --force pour l'écraser.")

    info = Info(constants.MAINNET_API_URL, skip_ws=True)
    print(f"Récupération des positions pour {address}...")
    user_state = info.spot_user_state(address)
    balances = user_state.get("balances", [])

    config = build_config(balances)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

    print(f"Fichier {path} généré avec {len(config['tokens'])} token(s).")
    return config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Génère config.json depuis les soldes Spot.")
    parser.add_argument("address", nargs="?", default=os.getenv("HYPERLIQUID_ADDRESS"),
                        help="Adresse publique Hyperliquid (ou variable HYPERLIQUID_ADDRESS).")
    parser.add_argument("--config", default=CONFIG_PATH, help="Chemin du fichier à générer.")
    parser.add_argument("--force", action="store_true", help="Écrase config.json s'il existe.")
    args = parser.parse_args(argv)

    if not args.address:
        print("Veuillez fournir une adresse (argument ou variable HYPERLIQUID_ADDRESS).")
        return 2

    try:
        init_config(args.address, args.config, force=args.force)
    except (ValueError, FileExistsError) as e:
        print(f"Erreur: {e}")
        return 1
    except Exception as e:  # noqa: BLE001 - feedback clair pour l'utilisateur final
        print(f"Erreur lors de l'initialisation (réseau/API): {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
