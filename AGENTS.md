# AGENTS.md — constitution agent (module Odoo)

Court, factuel, vivant. Module Odoo **19** en Docker. Si je te corrige sur une
convention, mets à jour ce fichier dans la foulée.

## Lancer / tester (FAITS)
- Stack dev : `./scripts/dev.sh` (port 8069, image construite, hot reload ; `--data=prod` pour souscriptions_prodlocal)
- Suite de tests COMPLÈTE (lourde, délibérée) : `./test.sh`
  → `odoo -d <db> -i <module> --test-enable --test-tags /<module> --stop-after-init`
- Le hook `Stop` ne lance QUE le gate rapide (syntaxe Python + XML bien formé). Les vrais tests = `./test.sh` + la CI.
- Lint/format : `ruff` (config dans `.pre-commit-config.yaml`).

## Structure (conventions Odoo)
- `__manifest__.py` : tenir `data` à jour pour CHAQUE nouveau fichier XML/CSV ; version `19.0.x.y.z`.
- `models/` (Python) · `views/` (XML) · `security/ir.model.access.csv` (OBLIGATOIRE pour tout nouveau modèle) · `data/` · `demo/` · `migrations/`.
- Pas de logique métier dans les vues. Étendre via `_inherit`, pas réécrire.
- Nouveau champ stocké → prévoir une migration dans `migrations/`.

## Skills vs MCP (le seuil — cf. recherche)
- Ce module est **greenfield (tu en possèdes la structure)** → les **skills statiques + ce fichier suffisent**. Pas de MCP.
- N'ajoute un **MCP live** (`tuanle96/mcp-odoo`, `uvx odoo-mcp --setup`, zéro Docker) QUE si tu dois raisonner sur une **instance / un schéma que tu n'as pas écrits** (modules OCA, Studio, debug d'une prod). Pas avant.

## Sécurité
- Jamais committer un `.env` (déjà en deny global). `gitleaks` tourne en pre-commit.
