#!/usr/bin/env bash
#
# Point d'entrée UNIQUE pour lancer le module en local : image CONSTRUITE
# (docker/Dockerfile — electricore-client présent) + hot reload, au-dessus de
# `docker compose`. Toute la config conteneur reste dans docker-compose.yml ;
# ce script ne fait que choisir la base/DB à charger et piloter compose.
#
#   ./scripts/dev.sh                  # mode demo (défaut) : souscriptions_demo + données de démo
#   ./scripts/dev.sh --data=demo      # idem, explicite
#   ./scripts/dev.sh --data=prod      # souscriptions_prodlocal, module installé SANS démo
#                                      # (pilotage souscriptions_migration : tranche suivante, pas ici)
#   ./scripts/dev.sh --reset          # repart d'une base vierge pour le mode choisi
#
# -> http://localhost:8069  (admin / admin)
#
# Remplace scripts/run-app.sh (image stock odoo:19, sans electricore-client).
#
# Un mode à la fois : les deux bases coexistent dans le même volume PostgreSQL,
# mais un seul service `odoo` tourne, filtré sur la base choisie
# (--db-filter, cf. docker-entrypoint-init.sh) — l'écran de login ne montre que
# cette base. Changer de mode = relancer avec l'autre --data.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE=(docker compose -f "$REPO_ROOT/docker/docker-compose.yml")

DATA=demo
RESET=

for arg in "$@"; do
    case "$arg" in
        --data=demo) DATA=demo ;;
        --data=prod) DATA=prod ;;
        --reset) RESET=1 ;;
        *)
            echo "Usage: $0 [--data=demo|prod] [--reset]" >&2
            exit 1
            ;;
    esac
done

if [ "$DATA" = "prod" ]; then
    export DB=souscriptions_prodlocal
    export LOAD_DEMO=
else
    export DB=souscriptions_demo
    export LOAD_DEMO=1
fi

if [ -n "$RESET" ]; then
    echo "Réinitialisation : suppression de la base '$DB' (l'autre mode n'est pas touché)..."
    "${COMPOSE[@]}" up -d db
    until "${COMPOSE[@]}" exec -T db pg_isready -U odoo -q 2>/dev/null; do sleep 1; done
    "${COMPOSE[@]}" exec -T db dropdb -U odoo --if-exists "$DB"
fi

echo ""
echo "==> Mode $DATA : base '$DB'$( [ -z "${LOAD_DEMO:-}" ] && echo ' (sans démo)' )"
echo "==> Odoo démarre sur http://localhost:8069  (admin / admin)"
echo "==> Ctrl-C pour arrêter ; ./scripts/dev.sh --data=$DATA --reset repart d'une base vierge."
echo ""
exec "${COMPOSE[@]}" up --build odoo
