#!/bin/bash
# Script pour réinitialiser complètement la démo
# Supprime toutes les données et recrée une base propre

set -e

echo "🔄 Réinitialisation complète de la démo Odoo..."
echo "⚠️  ATTENTION: Ceci va supprimer toutes les données!"
echo ""

# Demander confirmation
read -p "Êtes-vous sûr de vouloir continuer? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "❌ Réinitialisation annulée"
    exit 1
fi

# Vérifier que nous sommes dans le bon répertoire
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Erreur: Ce script doit être exécuté depuis le répertoire racine du projet"
    exit 1
fi

# Arrêter et supprimer les conteneurs et volumes
echo "🧹 Suppression des conteneurs et données existants..."
docker-compose down -v

# Relancer la démo complète
echo "🚀 Lancement de la démo avec données fraîches..."
./docker-demo.sh

echo ""
echo "✅ Réinitialisation terminée!"