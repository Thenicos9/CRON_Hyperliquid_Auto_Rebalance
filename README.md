# Hyperliquid Auto Rebalance Bot 🤖

Ce bot automatise le rebalancement de vos positions **Spot** sur Hyperliquid via GitHub Actions.

## Fonctionnement

Le bot tourne toutes les **7 minutes** via un GitHub Action (Cron job).
Il vérifie la valeur USD de vos positions spot et effectue un trade de rebalancement si les conditions sont remplies.

### Stratégie par défaut :
- **Cible** : Chaque position doit valoir environ **100$**.
- **Seuil** : Le rebalancement se déclenche si la position varie de **+/- 50%** (soit < 50$ ou > 150$).
- **Trade** : Le bot achète ou vend une tranche fixe de **12$**.

## Configuration

### 1. Secrets GitHub (Obligatoire)
Allez dans `Settings > Secrets and variables > Actions` et ajoutez :
- `HYPERLIQUID_SECRET_KEY` : Votre clé privée (format hex 0x...).
- `HYPERLIQUID_ADDRESS` : Votre adresse de wallet publique.

### 2. Fichier `config.json` (Optionnel)
Vous pouvez modifier les paramètres dans `config.json` :
- `target_value_usd` : Valeur cible en USD.
- `rebalance_threshold_pct` : Seuil de déclenchement (0.5 = 50%).
- `trade_size_usd` : Taille du trade de rebalancement.
- `assets` : Liste des coins à surveiller (ex: `["PURR", "HYPE"]`). Si vide, surveille tous vos avoirs spot.

## Installation

1. Clonez ce repo.
2. Configurez vos secrets sur GitHub.
3. Le bot commencera à tourner automatiquement toutes les 7 minutes.

---
*Note: Ce bot est fourni à titre informatif. Utilisez-le à vos propres risques. Assurez-vous d'avoir assez d'USDC sur votre compte spot pour les achats.*
