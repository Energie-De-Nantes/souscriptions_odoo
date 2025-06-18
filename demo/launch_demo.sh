#!/bin/bash

# Script de lancement rapide pour démo
DB_NAME="souscriptions_demo"
ADDONS_PATH="/home/virgile/addons_odoo,/usr/lib/python3/dist-packages/odoo/addons"

echo "🚀 Lancement Odoo avec données de démo..."
echo "Base de données: $DB_NAME"
echo "URL: http://localhost:8069"
echo "Login: admin / admin"
echo ""

odoo -d $DB_NAME \
     --addons-path="$ADDONS_PATH" \
     -i souscriptions \
     --load-language=fr_FR \
     --without-demo=False

echo "✅ Démo prête sur http://localhost:8069"