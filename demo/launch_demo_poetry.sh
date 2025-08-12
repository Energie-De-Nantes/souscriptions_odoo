#!/bin/bash

# Script de lancement pour démo avec Poetry
DB_NAME="souscriptions_demo"
ADDONS_PATH="/home/virgile/addons_odoo"

echo "🚀 Préparation de la démo Odoo avec Poetry..."
echo "Base de données: $DB_NAME"

# Vérifier si Poetry est disponible
if ! command -v poetry &> /dev/null; then
    echo "❌ Poetry n'est pas installé ou pas dans le PATH"
    exit 1
fi

# S'assurer que nous sommes dans le bon répertoire
cd "$(dirname "$0")/.." || exit

# Installer les dépendances si nécessaire
echo "📦 Vérification des dépendances Python..."
poetry install --no-interaction

# Vérifier si la base existe
if psql -lqt | cut -d \| -f 1 | grep -qw $DB_NAME; then
    echo "🗄️  Suppression de la base existante pour recréer avec les données de démo..."
    dropdb $DB_NAME 2>/dev/null || true
fi

echo "🗄️  Création d'une nouvelle base de données..."
createdb $DB_NAME

echo "📊 Installation du module..."
poetry run odoo -d $DB_NAME \
     --addons-path="$ADDONS_PATH" \
     -i souscriptions \
     --load-language=fr_FR \
     --stop-after-init

echo "📝 Chargement des données de démo..."
# Les données de démo sont chargées via le manifest avec l'option --without-demo=all
# On réinstalle le module pour forcer le chargement des données de démo
poetry run odoo -d $DB_NAME \
     --addons-path="$ADDONS_PATH" \
     -u souscriptions \
     --load-language=fr_FR \
     --stop-after-init

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

# Lancer le serveur en mode interactif avec Poetry
poetry run odoo -d $DB_NAME \
     --addons-path="$ADDONS_PATH" \
     --load-language=fr_FR \
     --dev=reload,xml,qweb