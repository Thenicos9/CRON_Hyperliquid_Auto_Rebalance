# Hyperliquid Auto Rebalance Bot (Production Ready) 🚀

Bot de gestion de portefeuille automatisé pour le marché **Spot** d'Hyperliquid. Ce bot maintient vos positions à une valeur cible définie, en vendant les surplus et en rachetant les baisses de manière disciplinée.

## ✨ Caractéristiques
- **Configurabilité Totale** : Paramètres globaux ou spécifiques par token.
- **Auto-Génération** : Script d'initialisation qui scanne votre wallet pour créer la config.
- **Sécurité API** : Gestion stricte des décimales (`szDecimals`) et des tailles minimales d'ordres (>10$).
- **Zéro Maintenance** : Tourne gratuitement sur GitHub Actions toutes les 7 minutes.
- **Slippage Contrôlé** : Ordres au marché avec protection de slippage de 1%.

## 🛠 Installation Rapide

### 1. Préparation du Wallet
Assurez-vous d'avoir :
- Une clé privée Hyperliquid (ou clé API).
- De l'USDC sur votre compte **Spot** pour les frais et les achats.

### 2. Configuration des Secrets GitHub
Dans votre repo : `Settings > Secrets and variables > Actions` :
- `HYPERLIQUID_SECRET_KEY` : Votre clé privée (0x...).
- `HYPERLIQUID_ADDRESS` : Votre adresse publique.

### 3. Initialisation de la Config
Vous pouvez lancer le script `init_config.py` localement pour générer votre `config.json` de base, puis le push sur le repo.

```bash
export HYPERLIQUID_ADDRESS=votre_adresse
python init_config.py
```

## ⚙️ Structure de `config.json`

```json
{
    "global": {
        "default_target_value_usd": 100.0,
        "default_rebalance_threshold_pct": 0.5,
        "default_trade_size_usd": 12.0,
        "min_order_usd": 11.0
    },
    "tokens": {
        "PURR": {
            "enabled": true,
            "target_value_usd": 150.0,
            "rebalance_threshold_pct": 0.3,
            "trade_size_usd": 20.0
        }
    }
}
```

## 🛡 Sécurité et Limites
- **Rate Limits** : Le bot effectue une pause entre chaque ordre.
- **Taille Min** : Le bot ne tentera jamais d'ordre < 10$ (limite Hyperliquid).
- **Précision** : Utilisation des `szDecimals` officiels d'Hyperliquid pour éviter les erreurs d'API.
