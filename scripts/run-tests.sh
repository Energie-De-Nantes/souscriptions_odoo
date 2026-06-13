#!/usr/bin/env bash
#
# Lance la suite de tests du module sur Odoo 19 via Docker.
#
# Le seul filtrage appliqué supprime les lignes de bruit docutils de la forme
# « <string>:N: (ERROR/3) ... » : elles proviennent du rendu RST de la
# description du module *core* `mail` d'Odoo (description invalide côté Odoo),
# n'ont aucun lien avec ce module et ne sont pas corrigeables ici. Ce sont les
# seules lignes retirées ; une vraie erreur de test est toujours préfixée d'un
# horodatage (« 2026-... ERROR test_db odoo... ») et n'est donc jamais masquée.
#
# Le code de sortie d'Odoo est préservé : un test en échec fait échouer le script.
#
# Usage :
#   ./scripts/run-tests.sh                       # toute la suite
#   TEST_TAGS=souscriptions_facturation ./scripts/run-tests.sh
#   LOG_LEVEL=info ./scripts/run-tests.sh

set -euo pipefail

NETWORK="${NETWORK:-odoo-test}"
PG="${PG:-souscriptions-pg}"
DB="${DB:-test_db}"
TEST_TAGS="${TEST_TAGS:-/souscriptions_odoo}"
LOG_LEVEL="${LOG_LEVEL:-test}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cleanup() {
    docker rm -f "$PG" >/dev/null 2>&1 || true
    docker network rm "$NETWORK" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create "$NETWORK" >/dev/null 2>&1 || true
docker rm -f "$PG" >/dev/null 2>&1 || true
docker run -d --name "$PG" --network "$NETWORK" \
    -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=odoo -e POSTGRES_DB=postgres \
    postgres:15 >/dev/null
until docker exec "$PG" pg_isready -U odoo -q 2>/dev/null; do sleep 1; done

docker run --rm --network "$NETWORK" \
    -e HOST="$PG" -e USER=odoo -e PASSWORD=odoo \
    -v "$REPO_ROOT:/mnt/extra-addons/souscriptions_odoo:ro" \
    odoo:19 odoo \
        --addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons \
        -d "$DB" -i souscriptions_odoo \
        --test-enable --test-tags "$TEST_TAGS" \
        --stop-after-init --log-level="$LOG_LEVEL" \
    2>&1 | grep -vE '^<string>:[0-9]+: \((ERROR|WARNING|INFO)'
