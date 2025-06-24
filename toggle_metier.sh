#!/bin/bash
# toggle_metier.sh - Active/désactive la partie métier du module souscriptions

MODE=$1

if [ "$MODE" = "enable" ]; then
    echo "Activation du module métier..."
    
    # Décommenter l'import métier dans models/__init__.py
    sed -i 's/# from \. import metier/from . import metier/' models/__init__.py
    
    # Décommenter les vues métier dans __manifest__.py
    sed -i '/"views\/metier/s/# //' __manifest__.py
    
    echo "Module métier activé."
    echo ""
    echo "Prochaines étapes :"
    echo "1. Redémarrer le serveur Odoo"
    echo "2. Mettre à jour le module avec : odoo-bin -u souscriptions"
    echo "3. Les modèles métier seront maintenant disponibles"
    
elif [ "$MODE" = "disable" ]; then
    echo "Désactivation du module métier..."
    
    # Commenter l'import métier
    sed -i 's/^from \. import metier/# from . import metier/' models/__init__.py
    
    # Commenter les vues métier
    sed -i '/"views\/metier/s/^/# /' __manifest__.py
    
    echo "Module métier désactivé."
    echo ""
    echo "ATTENTION : Si des données métier existent déjà dans la base,"
    echo "elles resteront présentes mais ne seront plus accessibles."
    echo ""
    echo "Prochaines étapes :"
    echo "1. Redémarrer le serveur Odoo"
    echo "2. Mettre à jour le module avec : odoo-bin -u souscriptions"
    
elif [ "$MODE" = "status" ]; then
    echo "Statut actuel du module métier :"
    echo "================================"
    
    if grep -q "^from \. import metier" models/__init__.py; then
        echo "✓ Import métier : ACTIF"
    else
        echo "✗ Import métier : INACTIF"
    fi
    
    if grep -q '^[[:space:]]*"views/metier' __manifest__.py; then
        echo "✓ Vues métier : ACTIVES"
    else
        echo "✗ Vues métier : INACTIVES"
    fi
    
else
    echo "Usage: $0 [enable|disable|status]"
    echo ""
    echo "  enable  - Active la partie métier du module"
    echo "  disable - Désactive la partie métier du module"
    echo "  status  - Affiche le statut actuel"
    echo ""
    echo "Exemple : ./toggle_metier.sh enable"
    exit 1
fi