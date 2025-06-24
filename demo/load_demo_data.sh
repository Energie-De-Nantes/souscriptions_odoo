#!/bin/bash

# Script pour charger les données de démo dans une base existante

DB_NAME="souscriptions_demo"
ADDONS_PATH="/home/virgile/addons_odoo,/usr/lib/python3/dist-packages/odoo/addons"

echo "📊 Chargement des données de démo dans la base $DB_NAME..."

# Charger les données de démo directement
odoo -d $DB_NAME \
     --addons-path="$ADDONS_PATH" \
     --load-language=fr_FR \
     --stop-after-init \
     --init=souscriptions \
     --without-demo=False

echo "✅ Données de démo chargées !"
echo ""
echo "Données disponibles :"
echo "  - 4 clients de test (Marie Dupont, Jean Martin, Boulangerie Bio, Sophie Leroy)"
echo "  - 4 souscriptions avec différents profils (BASE, HP/HC, PRO, Solidaire)"
echo "  - Grille de prix de démonstration"
echo ""
echo "Pour voir les données :"
echo "  odoo -d $DB_NAME --addons-path='$ADDONS_PATH'"