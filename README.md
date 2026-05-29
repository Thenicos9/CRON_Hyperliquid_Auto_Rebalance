# Hyperliquid Auto Rebalance Bot 🚀

Bot de gestion de portefeuille automatisé pour le marché **Spot** d'Hyperliquid.
Il maintient chaque position à une valeur cible en USD : il vend le surplus
quand une position dépasse la bande haute, et rachète quand elle passe sous la
bande basse.

> ⚠️ **Avertissement risque.** Ce bot envoie de **vrais ordres** avec de **vrais
> fonds** sur le mainnet. Le trading automatisé peut entraîner des pertes.
> Testez d'abord en `--dry-run`, commencez avec de petits montants, et n'utilisez
> que des fonds que vous pouvez vous permettre de perdre. Aucune garantie.

## ✨ Caractéristiques
- **Cibles configurables** par token (valeur cible, seuil, taille de trade).
- **Auto-génération** de la config en scannant votre wallet (`init_config.py`).
- **Cooldown anti-rebond** : évite de retrader le même token trop souvent.
- **Vérification de solde** avant chaque ordre (USDC pour un achat, token pour une vente).
- **Validation** stricte de la config et des variables d'environnement.
- **Détection des erreurs d'ordre** réelles (Hyperliquid renvoie `status: ok` même quand un ordre échoue).
- **Mode `--dry-run`** pour simuler sans risquer de fonds.
- **Notifications** Telegram / Discord (optionnelles).
- **Gestion fine des décimales** (`szDecimals`) et de la taille minimale (>10$).

## 📦 Installation

```bash
pip install -r requirements.txt          # runtime
pip install -r requirements-dev.txt      # + outils de test (optionnel)
```

## 🔐 Configuration des secrets

Le bot lit ses secrets depuis des variables d'environnement (jamais depuis un fichier versionné) :

| Variable | Obligatoire | Description |
|---|---|---|
| `HYPERLIQUID_ADDRESS` | oui | Votre adresse publique (`0x…`, 42 caractères). |
| `HYPERLIQUID_SECRET_KEY` | oui (sauf dry-run) | Clé privée **ou clé d'agent (API Wallet)**. |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | non | Pour les notifications Telegram. |
| `DISCORD_WEBHOOK_URL` | non | Pour les notifications Discord. |

> 🛡️ **Recommandé : utilisez une « API Wallet » (clé d'agent) plutôt que la clé
> privée de votre wallet principal.** Sur Hyperliquid, vous pouvez générer une
> clé d'agent qui peut **trader mais pas retirer** les fonds. En cas de fuite, le
> risque est très réduit. Renseignez alors `HYPERLIQUID_SECRET_KEY` avec cette
> clé d'agent et `HYPERLIQUID_ADDRESS` avec votre adresse principale.

Exemple en local :

```bash
export HYPERLIQUID_ADDRESS=0xVotreAdresse
export HYPERLIQUID_SECRET_KEY=0xVotreCleDAgent
```

## ⚙️ Génération de la configuration

`config.json` **n'est pas versionné** (voir `.gitignore`) car il reflète votre
stratégie personnelle. Générez-le localement :

```bash
python init_config.py 0xVotreAdresse
# ou, si HYPERLIQUID_ADDRESS est exporté :
python init_config.py
```

Un modèle est fourni dans [`config.example.json`](config.example.json).

### Paramètres

| Champ | Sens |
|---|---|
| `default_target_value_usd` | Valeur cible par défaut d'une position, en USD. |
| `default_rebalance_threshold_pct` | Demi-largeur de la bande (0.1 = ±10%). La position est rebalancée hors de `[cible×(1−seuil), cible×(1+seuil)]`. |
| `default_trade_size_usd` | Taille d'un ordre de rebalancing, en USD. |
| `min_order_usd` | Plancher de sécurité au-dessus de la limite Hyperliquid (10$). |
| `cooldown_minutes` | Délai minimum entre deux trades d'un même token. |
| `default_slippage_pct` | Slippage max accepté sur les ordres au marché (0.01 = 1%). |

Chaque token peut surcharger `target_value_usd`, `rebalance_threshold_pct`,
`trade_size_usd`, et être désactivé via `"enabled": false`.

## ▶️ Exécution

```bash
python rebalance.py --dry-run     # simulation, aucun ordre envoyé (clé non requise)
python rebalance.py               # exécution réelle
```

Le mode réel met à jour `rebalance_state.json` (suivi du cooldown) et envoie
une notification si des ordres ont été passés ou si une erreur survient.

## 🤖 Déploiement GitHub Actions (CRON)

Un workflow est fourni dans [`.github/workflows/rebalance.yml`](.github/workflows/rebalance.yml)
pour exécuter le bot automatiquement (~toutes les 7 minutes).

> ⚠️ **Activation manuelle obligatoire.** Pour des raisons de sécurité, le
> workflow doit être activé par vous-même dans l'onglet **Actions** du dépôt.
> N'activez ce CRON qu'en pleine connaissance des risques (ordres réels).
> GitHub peut par ailleurs retarder les exécutions planifiées : la fréquence
> de 7 minutes est « best-effort », pas garantie.

À configurer dans `Settings > Secrets and variables > Actions` :
- **Secrets** : `HYPERLIQUID_SECRET_KEY`, `HYPERLIQUID_ADDRESS` (+ secrets de notif. optionnels).
- **Variable** `CONFIG_JSON` : collez-y le contenu de votre `config.json`. Le
  workflow le reconstruit à chaque exécution (puisque le fichier n'est pas versionné).

Le workflow utilise `actions/cache` pour conserver `rebalance_state.json` entre
les exécutions, afin que le cooldown reste effectif malgré des runners éphémères.

## 🧪 Tests

```bash
python -m pytest
```

La suite couvre les calculs (`truncate_float`), la logique de décision
(`decide_action`), le cooldown, la validation de config/env, l'interprétation des
réponses d'ordre, et l'orchestration complète (`run_rebalance`) avec des
doublures d'API.

## 📁 Structure

```
rebalance.py          # bot principal (logique + exécution)
init_config.py        # génération de config.json depuis le wallet
config.example.json   # modèle de configuration
requirements*.txt     # dépendances runtime / dev
tests/                # tests unitaires et d'intégration
.github/workflows/    # workflow CRON (à activer manuellement)
```
