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
#   ./scripts/dev.sh --data=prod --light[=PAS]  # chargement rapide : 1 souscription sur PAS
#                                      # (défaut 10), cascade sur les collections liées
#   ./scripts/dev.sh --reset          # repart d'une base vierge pour le mode choisi
#
# Mode prod : pilote `../souscriptions_migration` (ADR 0003/0023, dépôt jetable **voisin**,
# jamais fusionné ici) en shell-out — transform -> load --cible vierge (base fraîche : rien
# à bind, `bind` sert le chemin bascule odoo.sh, hors sujet ici). Garde-fous fail-closed
# (charte migration) vérifiés avant ET après chargement : aucun mail sortant, aucun
# règlement SEPA groupé — une base non conforme arrête le script. Les crons tournent
# (--max-cron-threads=2 depuis le 19/07/2026) : le module en dépend (amorçage de
# campagne, vidanges, poll RSC — ADR 0035/0036) ; le fail-closed mail repose sur
# l'absence d'ir.mail_server (vérifiée ci-dessous) + aucun SMTP joignable du conteneur.
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
LIGHT=

for arg in "$@"; do
    case "$arg" in
        --data=demo) DATA=demo ;;
        --data=prod) DATA=prod ;;
        --reset) RESET=1 ;;
        --fresh) FRESH=1 ;;
        --light) LIGHT=10 ;;
        --light=*) LIGHT="${arg#--light=}" ;;
        *)
            echo "Usage: $0 [--data=demo|prod] [--reset] [--fresh] [--light[=PAS]]" >&2
            exit 1
            ;;
    esac
done

if [ -n "$FRESH" ] && [ "$DATA" != "prod" ]; then
    echo "--fresh n'a de sens qu'avec --data=prod." >&2
    exit 1
fi

if [ -n "$LIGHT" ] && [ "$DATA" != "prod" ]; then
    echo "--light n'a de sens qu'avec --data=prod." >&2
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
    # Odoo tient des connexions sur la base : l'arrêter d'abord, sinon dropdb échoue
    # (et un `up -d` ultérieur ne redémarrerait pas un conteneur déjà en route).
    "${COMPOSE[@]}" stop odoo
    "${COMPOSE[@]}" up -d db
    until "${COMPOSE[@]}" exec -T db pg_isready -U odoo -q 2>/dev/null; do sleep 1; done
    # --force (PG 13+) : coupe les sessions restantes (psql ouverts, etc.).
    "${COMPOSE[@]}" exec -T db dropdb -U odoo --if-exists --force "$DB"
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

# Les crons tournent volontairement (le module en dépend : amorçage, vidanges, poll RSC).
# Le fail-closed « aucun mail sortant » est porté par assert_garde_fous (ir.mail_server
# vide) — un mail mis en file sans serveur SMTP finit en exception, il ne sort pas.

assert_garde_fous() {
    # Garde-fous fail-closed niveau base (charte migration : aucun mail sortant, aucun SEPA
    # généré sur une cible qui porte de vraies données). Le compte SEPA se fait en deux temps :
    # Postgres résout TOUTES les tables d'une requête au parsing, donc un `CASE to_regclass(...)`
    # dans la même requête ne protège pas d'un `account_batch_payment` absent (module Enterprise,
    # jamais présent sur l'image community). Table absente = aucun SEPA possible = 0.
    local mail_servers sepa_table sepa_batches
    mail_servers=$("${COMPOSE[@]}" exec -T db psql -U odoo -d "$DB" -tAc \
        "SELECT count(*) FROM ir_mail_server" 2>/dev/null || echo ERR)
    sepa_table=$("${COMPOSE[@]}" exec -T db psql -U odoo -d "$DB" -tAc \
        "SELECT to_regclass('public.account_batch_payment')" 2>/dev/null || echo ERR)
    if [ "$sepa_table" = "ERR" ]; then
        sepa_batches=ERR
    elif [ -z "$sepa_table" ]; then
        sepa_batches=0
    else
        sepa_batches=$("${COMPOSE[@]}" exec -T db psql -U odoo -d "$DB" -tAc \
            "SELECT count(*) FROM account_batch_payment" 2>/dev/null || echo ERR)
    fi
    if [ "$mail_servers" != "0" ]; then
        echo "Garde-fou violé ($1) : ir.mail_server non vide sur '$DB' (mail sortant configuré)." >&2
        exit 1
    fi
    if [ "$sepa_batches" != "0" ]; then
        echo "Garde-fou violé ($1) : des règlements SEPA groupés existent sur '$DB'." >&2
        exit 1
    fi
    echo "==> Garde-fous OK ($1) : mail sortant vide, aucun SEPA (crons actifs, sans transport mail)."
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
    light_args=()
    if [ -n "$LIGHT" ]; then light_args=(--light "$LIGHT"); fi
    uv run --with pydantic-settings --no-project python -m migration load --rapport "$rapport" "${light_args[@]}"
)

assert_garde_fous "après chargement"

echo ""
echo "==> Données de prod chargées. Odoo tourne sur http://localhost:8069  (admin / admin)"
echo "==> Ctrl-C arrête le suivi des logs (les conteneurs restent démarrés ; --reset repart d'une base vierge)."
echo ""
exec "${COMPOSE[@]}" logs -f odoo
