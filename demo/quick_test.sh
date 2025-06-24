#!/bin/bash

# Script de test rapide - utilise une base existante
DB_NAME="souscriptions_demo"
ADDONS_PATH="/home/virgile/addons_odoo,/usr/lib/python3/dist-packages/odoo/addons"

echo "🚀 Test rapide - mise à jour du module..."

# Vérifier si la base existe
if ! psql -lqt | cut -d \| -f 1 | grep -qw $DB_NAME; then
    echo "❌ Base $DB_NAME n'existe pas. Utilise ./demo/launch_demo.sh pour la créer."
    exit 1
fi

echo "📊 Mise à jour du module souscriptions..."
odoo -d $DB_NAME \
     --addons-path="$ADDONS_PATH" \
     -u souscriptions \
     --stop-after-init

echo "✅ Module mis à jour ! Lancement du serveur..."
echo "URL: http://localhost:8069"
echo "Login: admin / admin"

# Lancer le serveur
odoo -d $DB_NAME \
     --addons-path="$ADDONS_PATH" \
     --load-language=fr_FR