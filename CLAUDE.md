# CLAUDE.md

Guide pour les agents (Claude Code) travaillant sur ce dépôt.

## Vue d'ensemble

Bot de **rebalancing automatique du portefeuille Spot Hyperliquid**. À chaque
exécution (CRON), il ramène chaque position vers une valeur cible en USD : il
**vend** au-dessus de la bande haute, **rachète** sous la bande basse.

⚠️ **Le bot envoie de vrais ordres avec de vrais fonds (mainnet).** Toute
modification de la logique de trading doit être prudente, testée, et de
préférence vérifiée d'abord en `--dry-run`.

## Architecture (volontairement simple — scripts, pas de package)

| Fichier | Rôle |
|---|---|
| `rebalance.py` | Bot principal : chargement/validation config, données de marché, décision, exécution des ordres, cooldown, notifications. |
| `init_config.py` | Génère `config.json` en scannant les soldes Spot du wallet. |
| `config.example.json` | Modèle de configuration versionnable. |
| `tests/` | `test_rebalance.py` (fonctions pures) + `test_run_rebalance.py` (orchestration avec doublures d'API). |
| `.github/workflows/rebalance.yml` | Workflow CRON (~7 min), **à activer manuellement**. |

### Principe de conception clé
La logique métier est isolée dans des **fonctions pures et testables** :
`decide_action`, `truncate_float`, `cooldown_active`, `order_result_status`,
`validate_config`, `validate_env`, `is_valid_eth_address`. Les I/O réseau
(`Info`, `Exchange`) sont injectées dans `run_rebalance(...)`, ce qui permet de
la tester avec des fakes (voir `tests/test_run_rebalance.py`).
**Garder cette séparation** : toute nouvelle logique de décision doit être pure
et couverte par un test.

## Commandes

```bash
pip install -r requirements-dev.txt   # deps runtime + test
python -m pytest                      # lancer la suite (doit rester verte)
python rebalance.py --dry-run         # simulation, aucun ordre (clé non requise)
python rebalance.py                   # exécution réelle
python init_config.py 0xAdresse       # générer config.json
```

## Secrets & configuration

- Secrets via **variables d'environnement uniquement** :
  `HYPERLIQUID_ADDRESS`, `HYPERLIQUID_SECRET_KEY` (clé d'agent recommandée),
  et optionnellement `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`/`DISCORD_WEBHOOK_URL`.
- **`config.json`, `rebalance_state.json`, `.env` ne sont JAMAIS versionnés**
  (voir `.gitignore`). Ne jamais les committer.
- Sur GitHub Actions, `config.json` est reconstruit depuis la **variable de
  dépôt `CONFIG_JSON`** ; l'état (`rebalance_state.json`) est conservé via
  `actions/cache`.

## Détails à ne pas casser

- **Cooldown** : `rebalance_state.json` stocke `{"last_trade": {coin: ts_ms}}`.
  Le cooldown n'est posé **qu'en cas de succès** d'ordre.
- **Réponses d'ordre** : Hyperliquid renvoie souvent `{"status":"ok"}` même
  quand l'ordre échoue ; toujours passer par `order_result_status()`.
- **Vérif de solde** : avant un BUY (USDC) et un SELL (token) — ne pas retirer.
- **Décimales** : utiliser `truncate_float` avec `szDecimals` ; un ordre tronqué
  à 0 doit être ignoré.
- **`--dry-run`** ne doit jamais créer d'`Exchange` ni envoyer d'ordre.

## Conventions

- Python 3.11+, annotations de type, docstrings sur les fonctions publiques.
- Messages utilisateur et commentaires en **français** (cohérence du dépôt).
- Toute modification doit garder `python -m pytest` vert.

## Git

- Développer sur une branche dédiée, jamais directement sur `main`.
- Ne pas committer de secrets ni `config.json`/`rebalance_state.json`.
