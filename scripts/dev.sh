#!/usr/bin/env bash
#
# Point d'entrée UNIQUE pour lancer le module en local : image CONSTRUITE
# (docker/Dockerfile — electricore-client présent) + hot reload, au-dessus de
# `docker compose`. Toute la config conteneur reste dans docker-compose.yml ;
# ce script ne fait que choisir la base/DB à charger et piloter compose.
#
#   ./scripts/dev.sh                  # mode demo (défaut) : souscriptions_demo + données de démo
#   ./scripts/dev.sh --data=demo      # idem, explicite
#   ./scripts/dev.sh --data=prod      # souscriptions_prodlocal, module installé SANS démo,
#                                      # peuplée de vraies souscriptions via ../souscriptions_migration
#                                      # (dernier snapshot déjà présent : hors-ligne, sans secret)
#   ./scripts/dev.sh --data=prod --fresh  # idem + extract prod frais au préalable — requiert
#                                      # PROD__URL/PROD__DB/PROD__LOGIN/PROD__PASSWORD en env
#                                      # (jamais committés ; pass-cli `pr` ou .env chargé au préalable)
#   ./scripts/dev.sh --reset          # repart d'une base vierge pour le mode choisi
#
# Mode prod : pilote `../souscriptions_migration` (ADR 0003/0023, dépôt jetable **voisin**,
# jamais fusionné ici) en shell-out — transform -> load --cible vierge (base fraîche : rien
# à bind, `bind` sert le chemin bascule odoo.sh, hors sujet ici). Garde-fous fail-closed
# (charte migration) vérifiés avant ET après chargement : crons coupés, aucun mail sortant,
# aucun règlement SEPA groupé — une base non conforme arrête le script.
#
# Secrets electricore (ELECTRICORE_URL / _API_KEY) : injectés depuis Proton Pass —
#   pr ./scripts/dev.sh              # pass-cli résout .env.pass -> env shell -> pass-through compose -> conteneur
# Sans `pr` : vars vides -> intégration electricore désactivée (repli, ADR-0024), pas de crash.
# Voir docs/adr/0026 + electricore ADR-0056.
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
# Chemin RELATIF au dépôt (contrat de layout : dépôts voisins), jamais celui du
# worktree courant — cf. commentaire d'en-tête.
MIGRATION_DIR="$REPO_ROOT/../souscriptions_migration"

DATA=demo
RESET=
FRESH=

for arg in "$@"; do
    case "$arg" in
        --data=demo) DATA=demo ;;
        --data=prod) DATA=prod ;;
        --reset) RESET=1 ;;
        --fresh) FRESH=1 ;;
        *)
            echo "Usage: $0 [--data=demo|prod] [--reset] [--fresh]" >&2
            exit 1
            ;;
    esac
done

if [ -n "$FRESH" ] && [ "$DATA" != "prod" ]; then
    echo "--fresh n'a de sens qu'avec --data=prod." >&2
    exit 1
fi

if [ "$DATA" = "prod" ]; then
    export DB=souscriptions_prodlocal
    export LOAD_DEMO=

    # Préconditions vérifiées AVANT tout docker compose (échec bruyant et immédiat,
    # jamais un extract/chargement partiel) : dépôt voisin présent, et si --fresh,
    # vrais secrets prod déjà en environnement.
    if [ ! -d "$MIGRATION_DIR" ]; then
        echo "Dépôt '../souscriptions_migration' introuvable (chemin attendu : $MIGRATION_DIR)." >&2
        echo "Cloner Energie-De-Nantes/souscriptions_migration en voisin de ce dépôt avant --data=prod." >&2
        exit 1
    fi

    if [ -n "$FRESH" ]; then
        manquantes=()
        for var in PROD__URL PROD__DB PROD__LOGIN PROD__PASSWORD; do
            [ -n "${!var:-}" ] || manquantes+=("$var")
        done
        if [ "${#manquantes[@]}" -gt 0 ]; then
            echo "--fresh requiert les identifiants prod en environnement (jamais committés) : ${manquantes[*]} manquant(s)." >&2
            echo "Charger un .env non commité, ou lancer via pass-cli : pr ./scripts/dev.sh --data=prod --fresh" >&2
            exit 1
        fi
    fi
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

if [ "$DATA" != "prod" ]; then
    exec "${COMPOSE[@]}" up --build odoo
fi

# --- Mode prod : bring-up détaché, câblage souscriptions_migration, garde-fous ---

# Garde-fou statique : crons coupés au niveau serveur (docker-compose.yml, partagé par
# les deux modes) — vérifié ici pour que --data=prod s'arrête si jamais retiré.
if ! grep -q -- '--max-cron-threads=0' "$REPO_ROOT/docker/docker-compose.yml"; then
    echo "Garde-fou violé : --max-cron-threads=0 absent de docker-compose.yml (crons potentiellement actifs)." >&2
    exit 1
fi

assert_garde_fous() {
    # Garde-fous fail-closed niveau base (charte migration : aucun mail sortant, aucun SEPA
    # généré sur une cible qui porte de vraies données). `to_regclass` rend le compte SEPA
    # robuste à un `account_batch_payment` absent (module non chargé) sans faire échouer la requête.
    local mail_servers sepa_batches
    mail_servers=$("${COMPOSE[@]}" exec -T db psql -U odoo -d "$DB" -tAc \
        "SELECT count(*) FROM ir_mail_server" 2>/dev/null || echo ERR)
    sepa_batches=$("${COMPOSE[@]}" exec -T db psql -U odoo -d "$DB" -tAc \
        "SELECT CASE WHEN to_regclass('public.account_batch_payment') IS NULL THEN 0 ELSE (SELECT count(*) FROM account_batch_payment) END" 2>/dev/null || echo ERR)
    if [ "$mail_servers" != "0" ]; then
        echo "Garde-fou violé ($1) : ir.mail_server non vide sur '$DB' (mail sortant configuré)." >&2
        exit 1
    fi
    if [ "$sepa_batches" != "0" ]; then
        echo "Garde-fou violé ($1) : des règlements SEPA groupés existent sur '$DB'." >&2
        exit 1
    fi
    echo "==> Garde-fous OK ($1) : crons coupés, mail sortant vide, aucun SEPA."
}

"${COMPOSE[@]}" up -d --build odoo

echo "==> Attente de l'installation du module dans '$DB'..."
etat=""
for _ in $(seq 1 150); do
    etat=$("${COMPOSE[@]}" exec -T db psql -U odoo -d "$DB" -tAc \
        "SELECT state FROM ir_module_module WHERE name='souscriptions_odoo'" 2>/dev/null || true)
    [ "$etat" = "installed" ] && break
    sleep 2
done
if [ "$etat" != "installed" ]; then
    echo "souscriptions_odoo n'est pas passé à l'état 'installed' dans '$DB' (état observé : '${etat:-absent}')." >&2
    exit 1
fi
echo "==> Module installé."

assert_garde_fous "avant chargement"

(
    cd "$MIGRATION_DIR"

    if [ -n "$FRESH" ]; then
        echo "==> --fresh : extraction d'un nouveau snapshot depuis la prod..."
        uv run --with pydantic-settings --no-project python -m migration extract
    else
        echo "==> Peuplement hors-ligne depuis le dernier snapshot de souscriptions_migration/snapshots/"
    fi

    echo "==> transform (dernier snapshot)..."
    uv run --no-project python -m migration transform

    rapport="$(ls -t rapports/transform_*.json 2>/dev/null | head -1 || true)"
    if [ -z "$rapport" ]; then
        echo "Aucun rapport transform_*.json sous $MIGRATION_DIR/rapports/ après transform." >&2
        exit 1
    fi

    echo "==> load --rapport $rapport (cible vierge)..."
    # migration/config.py exige PROD__* ET DEV__* (schéma pydantic non conditionnel) même si
    # `load` ne lit que .dev — hors --fresh, des valeurs bidon suffisent (jamais envoyées sur
    # le réseau, jamais des secrets réels). DEV__* : contrat cible posé par cette tranche.
    : "${PROD__URL:=offline}" "${PROD__DB:=offline}" "${PROD__LOGIN:=offline}" "${PROD__PASSWORD:=offline}"
    export PROD__URL PROD__DB PROD__LOGIN PROD__PASSWORD
    export DEV__URL="http://localhost:8069"
    export DEV__DB="$DB"
    export DEV__LOGIN=admin
    export DEV__PASSWORD=admin
    uv run --with pydantic-settings --no-project python -m migration load --rapport "$rapport"
)

assert_garde_fous "après chargement"

echo ""
echo "==> Données de prod chargées. Odoo tourne sur http://localhost:8069  (admin / admin)"
echo "==> Ctrl-C arrête le suivi des logs (les conteneurs restent démarrés ; --reset repart d'une base vierge)."
echo ""
exec "${COMPOSE[@]}" logs -f odoo
