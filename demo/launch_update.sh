#!/bin/bash

# Script de lancement rapide SANS reset de la base
DB_NAME="souscriptions_demo"
ADDONS_PATH="/home/virgile/addons_odoo,/usr/lib/python3/dist-packages/odoo/addons"

echo "🔄 Mise à jour du module sans reset de la base..."
echo "Base de données: $DB_NAME"

# Vérifier que la base existe
if ! psql -lqt | cut -d \| -f 1 | grep -qw $DB_NAME; then
    echo "❌ La base $DB_NAME n'existe pas."
    echo "Utilisez ./demo/launch_demo.sh pour créer la base avec les données de démo."
    exit 1
fi

echo "📊 Mise à jour du module..."
odoo -d $DB_NAME \
     --addons-path="$ADDONS_PATH" \
     -u souscriptions \
     --load-language=fr_FR \
     --stop-after-init

echo ""
echo "✅ Module mis à jour ! Lancement du serveur..."
echo "URL: http://localhost:8071"
echo "Login: admin / admin"
echo ""
echo "Espace client disponible à : http://localhost:8071/espace-client"
echo ""

# Lancer le serveur en mode interactif
odoo -d $DB_NAME \
     --addons-path="$ADDONS_PATH" \
     --load-language=fr_FR \
     --http-port=8071