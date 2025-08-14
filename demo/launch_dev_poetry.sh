#!/bin/bash

# Script de lancement pour développement avec Poetry et rechargement automatique
DB_NAME="${1:-souscriptions_demo}"  # Permet de spécifier une autre base si besoin
ADDONS_PATH="/home/virgile/addons_odoo"

echo "🔧 Lancement d'Odoo en mode développement avec Poetry..."
echo "Base de données: $DB_NAME"
echo ""

# Vérifier si Poetry est disponible
if ! command -v poetry &> /dev/null; then
    echo "❌ Poetry n'est pas installé ou pas dans le PATH"
    exit 1
fi

# S'assurer que nous sommes dans le bon répertoire
cd "$(dirname "$0")/.." || exit

# Vérifier que les dépendances sont installées
echo "📦 Vérification des dépendances Python..."
poetry install --no-interaction

# Vérifier si la base existe
if ! psql -lqt | cut -d \| -f 1 | grep -qw $DB_NAME; then
    echo "⚠️  La base de données $DB_NAME n'existe pas."
    echo "Voulez-vous la créer ? (y/n)"
    read -r response
    if [[ "$response" == "y" ]]; then
        createdb $DB_NAME
        echo "✅ Base de données créée"
        
        # Installer le module
        echo "📊 Installation du module souscriptions_odoo..."
        poetry run odoo -d $DB_NAME \
             --addons-path="$ADDONS_PATH" \
             -i souscriptions_odoo \
             --load-language=fr_FR \
             --stop-after-init
    else
        echo "Annulation..."
        exit 1
    fi
fi

echo ""
echo "🚀 Lancement du serveur en mode développement..."
echo "URL: http://localhost:8069"
echo "Login: admin / admin"
echo ""
echo "Mode développement activé :"
echo "  - Rechargement automatique des fichiers Python"
echo "  - Rechargement des vues XML"
echo "  - Mode debug QWeb activé"
echo ""
echo "Appuyez sur Ctrl+C pour arrêter le serveur"
echo ""

# Lancer le serveur avec tous les options de développement
poetry run odoo -d $DB_NAME \
     --addons-path="$ADDONS_PATH" \
     --load-language=fr_FR \
     --dev=reload,xml,qweb \
     --log-level=debug