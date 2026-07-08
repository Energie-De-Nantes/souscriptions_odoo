#!/bin/bash
set -e

# Entrypoint de développement : garantit que la base $DB existe ET que le
# module y est installé (avec la démo si LOAD_DEMO), puis lance le serveur Odoo.
#
# Paramètres (env) :
# - DB         : nom de la base (défaut souscriptions_demo). Un mode à la fois :
#                souscriptions_demo et souscriptions_prodlocal coexistent dans
#                le même volume PG mais sont servies séparément (--db-filter).
# - LOAD_DEMO  : active le chargement de la démo (défaut activé). LOAD_DEMO=
#                (vide, explicitement mis à vide par l'appelant) installe le
#                module SANS charger la démo.
#
# Auto-réparant : la condition d'installation porte sur l'ÉTAT DU MODULE, pas sur
# la simple existence de la base. Une base résiduelle laissée à moitié initialisée
# (ex. créée par un ancien entrypoint cassé : base présente, module non installé)
# est donc rattrapée au lieu d'être servie vide (sinon : modèle `grille.prix`
# absent → 404). Plus besoin de `down -v`.
#
# Notes :
# - Le module s'appelle `souscriptions_odoo` (pas `souscriptions`).
# - Dans ce harnais, `-i` ne charge PAS les fichiers `demo:` du manifeste ; on les
#   charge explicitement via `force_demo` dans un `odoo shell`. On ne ré-écrit donc
#   plus de données de démo à la main : tout vient de `demo/*.xml`.

DB="${DB:-souscriptions_demo}"
# Expansion SANS ':' : seule l'ABSENCE de la variable applique le défaut ; un
# LOAD_DEMO= (vide) explicite reste vide, donc désactive la démo (cf. mode prod).
LOAD_DEMO="${LOAD_DEMO-1}"

wait_for_postgres() {
    echo "Attente de PostgreSQL..."
    export PGPASSWORD=$PASSWORD
    until psql -h "$HOST" -U "$USER" -d postgres -c '\q' 2>/dev/null; do
        echo -n "."
        sleep 1
    done
    echo " PostgreSQL prêt!"
}

wait_for_postgres

export PGPASSWORD=$PASSWORD

# 1. Garantir l'existence de la base (sans rien présumer de son contenu).
if ! psql -h "$HOST" -U "$USER" -d postgres -lqt | cut -d \| -f 1 | grep -qw "$DB"; then
    echo "🗄️  Création de la base '$DB'..."
    createdb -h "$HOST" -U "$USER" "$DB"
fi

# 2. Le module est-il réellement installé ? (base vide => table absente => vide)
module_state=$(psql -h "$HOST" -U "$USER" -d "$DB" -tAc \
    "SELECT state FROM ir_module_module WHERE name='souscriptions_odoo'" 2>/dev/null || true)

if [ "$module_state" = "installed" ]; then
    echo "✅ souscriptions_odoo déjà installé dans '$DB'"
else
    echo "📦 souscriptions_odoo non installé (état : '${module_state:-absent}') — installation..."
    odoo --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD" \
         -d "$DB" -i souscriptions_odoo --load-language=fr_FR --stop-after-init

    if [ "$LOAD_DEMO" ]; then
        echo "📊 Chargement des données de démo du manifeste (force_demo)..."
        odoo shell --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD" -d "$DB" <<'PY'
import odoo.modules.loading as loading
loading.force_demo(env)
env.cr.commit()
print("✅ Données de démo chargées (grilles, souscriptions, périodes…)")
PY
    fi
    echo "✅ Base '$DB' prête"
fi

# La commande compose commence historiquement par « odoo » ; on le retire car on
# relance odoo nous-mêmes ci-dessous (sinon : « unrecognized parameters: odoo »).
if [ "$1" = "odoo" ]; then
    shift
fi

exec odoo --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD" \
          -d "$DB" --db-filter="^${DB}$" "$@"
