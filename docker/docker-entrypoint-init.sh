#!/bin/bash
set -e

# Entrypoint de développement : au premier lancement, crée la base, installe
# souscriptions_odoo et charge les données de démo du *manifeste* (source unique),
# puis lance le serveur Odoo. Aux lancements suivants, démarre directement.
#
# Notes :
# - Le module s'appelle `souscriptions_odoo` (pas `souscriptions`).
# - Dans ce harnais, `-i` ne charge PAS les fichiers `demo:` du manifeste ; on les
#   charge explicitement via `force_demo` dans un `odoo shell`. On ne ré-écrit donc
#   plus de données de démo à la main : tout vient de `demo/*.xml`.

DB=souscriptions_demo

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
if psql -h "$HOST" -U "$USER" -d postgres -lqt | cut -d \| -f 1 | grep -qw "$DB"; then
    echo "✅ Base '$DB' déjà initialisée"
else
    echo "🗄️  Création de la base + installation de souscriptions_odoo..."
    createdb -h "$HOST" -U "$USER" "$DB"
    odoo --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD" \
         -d "$DB" -i souscriptions_odoo --load-language=fr_FR --stop-after-init

    echo "📊 Chargement des données de démo du manifeste (force_demo)..."
    odoo shell --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD" -d "$DB" <<'PY'
import odoo.modules.loading as loading
loading.force_demo(env)
env.cr.commit()
print("✅ Données de démo chargées (grilles, souscriptions, périodes…)")
PY
    echo "✅ Base '$DB' prête"
fi

# La commande compose commence historiquement par « odoo » ; on le retire car on
# relance odoo nous-mêmes ci-dessous (sinon : « unrecognized parameters: odoo »).
if [ "$1" = "odoo" ]; then
    shift
fi

exec odoo --db_host="$HOST" --db_user="$USER" --db_password="$PASSWORD" \
          -d "$DB" --db-filter="^${DB}$" "$@"
