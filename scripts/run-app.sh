#!/usr/bin/env bash
#
# Lance une instance Odoo 19 vivante avec le module + données de démo, pour
# explorer l'interface dans le navigateur.
#
#   ./scripts/run-app.sh
#   -> http://localhost:8069   (login: admin / mot de passe: admin)
#
# La base PostgreSQL est persistée dans un volume Docker : au premier lancement
# le module est installé avec les données de démo ; aux lancements suivants la
# base existante est réutilisée (les modifications faites dans l'UI sont
# conservées). Ctrl-C arrête le serveur ; les conteneurs restent (relancer le
# script repart de la même base).
#
# Pour repartir de zéro :
#   ./scripts/run-app.sh --reset
#
# Variables : PORT (défaut 8069), DB (défaut souscriptions_demo).

set -euo pipefail

NETWORK="souscriptions-app-net"
PG="souscriptions-app-pg"
APP="souscriptions-app"
PGVOL="souscriptions-app-pgdata"
DB="${DB:-souscriptions_demo}"
PORT="${PORT:-8069}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADDONS="--addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons"
MOUNT="$REPO_ROOT:/mnt/extra-addons/souscriptions_odoo:ro"

if [ "${1:-}" = "--reset" ]; then
    echo "Réinitialisation : suppression des conteneurs et du volume de données..."
    docker rm -f "$APP" "$PG" >/dev/null 2>&1 || true
    docker volume rm "$PGVOL" >/dev/null 2>&1 || true
    docker network rm "$NETWORK" >/dev/null 2>&1 || true
fi

docker network create "$NETWORK" >/dev/null 2>&1 || true

# PostgreSQL (volume persistant)
if [ -z "$(docker ps -q -f name="^${PG}$")" ]; then
    if [ -n "$(docker ps -aq -f name="^${PG}$")" ]; then
        docker start "$PG" >/dev/null
    else
        docker run -d --name "$PG" --network "$NETWORK" \
            -v "$PGVOL:/var/lib/postgresql/data" \
            -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=odoo -e POSTGRES_DB=postgres \
            postgres:15 >/dev/null
    fi
fi
until docker exec "$PG" pg_isready -U odoo -q 2>/dev/null; do sleep 1; done

# Premier lancement : installer le module avec les données de démo.
# On laisse Odoo créer lui-même la base (ce qui active le chargement des
# données de démo) ; ne PAS pré-créer la base avec createdb, sinon la démo
# n'est pas chargée.
if ! docker exec "$PG" psql -U odoo -lqt | cut -d'|' -f1 | grep -qw "$DB"; then
    echo "Première installation de souscriptions_odoo (avec données de démo)..."
    # --with-demo : Odoo 19 ne charge plus les données de démo par défaut.
    docker run --rm --network "$NETWORK" -e HOST="$PG" -e USER=odoo -e PASSWORD=odoo \
        -v "$MOUNT" odoo:19 odoo $ADDONS \
        -d "$DB" -i souscriptions_odoo --with-demo --load-language=fr_FR --stop-after-init \
        2>&1 | grep -vE '^<string>:[0-9]+: \((ERROR|WARNING|INFO)' || true
fi

echo ""
echo "==> Odoo démarre sur http://localhost:${PORT}  (admin / admin)"
echo "==> Ctrl-C pour arrêter."
echo ""
docker rm -f "$APP" >/dev/null 2>&1 || true
exec docker run --rm --name "$APP" --network "$NETWORK" -p "${PORT}:8069" \
    -e HOST="$PG" -e USER=odoo -e PASSWORD=odoo \
    -v "$MOUNT" odoo:19 odoo $ADDONS \
    -d "$DB" --db-filter="^${DB}\$"
