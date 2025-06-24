#!/bin/bash

# Script de lancement rapide pour démo
DB_NAME="souscriptions_demo"
ADDONS_PATH="/home/virgile/addons_odoo,/usr/lib/python3/dist-packages/odoo/addons"

echo "🚀 Préparation de la démo Odoo avec données de test..."
echo "Base de données: $DB_NAME"

# Vérifier si la base existe
if psql -lqt | cut -d \| -f 1 | grep -qw $DB_NAME; then
    echo "🗄️  Suppression de la base existante pour recréer avec les données de démo..."
    dropdb $DB_NAME 2>/dev/null || true
fi

echo "🗄️  Création d'une nouvelle base de données..."
createdb $DB_NAME

echo "📊 Installation du module..."
odoo -d $DB_NAME \
     --addons-path="$ADDONS_PATH" \
     -i souscriptions \
     --load-language=fr_FR \
     --stop-after-init

echo "📝 Création des données de démo..."
./demo/create_demo_via_shell.sh

echo ""
echo "✅ Démo prête ! Lancement du serveur..."
echo "URL: http://localhost:8069"
echo "Login: admin / admin"
echo ""
echo "Données de démo disponibles :"
echo "  - 4 clients (particuliers et PRO)"
echo "  - 4 souscriptions avec différents profils"
echo "  - Grille de prix de démonstration"
echo ""

# Lancer le serveur en mode interactif
odoo -d $DB_NAME \
     --addons-path="$ADDONS_PATH" \
     --load-language=fr_FR