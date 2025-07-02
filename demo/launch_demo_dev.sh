#!/bin/bash

# Script de lancement rapide pour développement avec auto-reload
DB_NAME="souscriptions_demo"
ADDONS_PATH="/home/virgile/addons_odoo,/usr/lib/python3/dist-packages/odoo/addons"

echo "🚀 Lancement d'Odoo en mode développement avec auto-reload..."
echo "Base de données: $DB_NAME"
echo ""

# Vérifier si watchdog est installé
if python3 -c "import watchdog" 2>/dev/null; then
    echo "✅ watchdog détecté - auto-reload activé"
    echo ""
    echo "🔄 Modifications détectées automatiquement pour:"
    echo "   - Fichiers Python (.py)"
    echo "   - Fichiers XML (vues, menus, etc.)"
    echo "   - Templates QWeb"
    echo ""
else
    echo "⚠️  watchdog non trouvé - auto-reload désactivé"
    exit 1
fi

echo "📌 Raccourcis utiles:"
echo "   - Ctrl+C pour arrêter le serveur"
echo "   - Les changements Python rechargent le serveur automatiquement"
echo "   - Les changements XML sont appliqués au refresh du navigateur"
echo ""
echo "URL: http://localhost:8069"
echo "Login: admin / admin"
echo ""

# Lancer le serveur avec auto-reload complet
odoo -d $DB_NAME \
     --addons-path="$ADDONS_PATH" \
     --load-language=fr_FR \
     --dev=reload,xml,qweb