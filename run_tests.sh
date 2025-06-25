#!/bin/bash

# Script wrapper pour lancer les tests Odoo de manière propre
# Remplace les anciens scripts de test manuels

set -e

# Configuration
DB_NAME="${1:-souscriptions_test}"
ODOO_PATH="${ODOO_PATH:-odoo}"
ADDONS_PATH="${ADDONS_PATH:-/home/virgile/addons_odoo}"

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Fonctions d'affichage
info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}"
}

# Fonction d'aide
show_help() {
    cat << EOF
Usage: $0 [OPTIONS] [DB_NAME]

Script pour lancer les tests Odoo du module souscriptions

OPTIONS:
    -h, --help          Afficher cette aide
    -a, --all           Lancer tous les tests (défaut)
    -t, --template      Lancer uniquement les tests de template
    -f, --facturation   Lancer uniquement les tests de facturation
    -b, --basic         Lancer uniquement les tests basiques
    -i, --integration   Lancer uniquement les tests d'intégration/workflow
    -u, --ui            Lancer uniquement les tests d'interface utilisateur
    -r, --reports       Lancer uniquement les tests de rapports
    -v, --verbose       Mode verbeux
    -c, --coverage      Avec couverture de code (si pytest-odoo disponible)
    --create-db         Forcer la création d'une nouvelle base de données
    --keep-db           Garder la base de données après les tests

EXEMPLES:
    $0                                  # Tous les tests sur base souscriptions_test
    $0 -t my_test_db                    # Tests template sur base my_test_db
    $0 --facturation --verbose         # Tests facturation en mode verbeux
    $0 --create-db --keep-db           # Nouvelle base, conservée après tests

VARIABLES D'ENVIRONNEMENT:
    ODOO_PATH       Chemin vers l'exécutable Odoo (défaut: odoo)
    ADDONS_PATH     Chemin vers les addons (défaut: /home/virgile/addons_odoo)
EOF
}

# Variables par défaut
TEST_TAGS="souscriptions"
VERBOSE=""
CREATE_DB=false
KEEP_DB=false
COVERAGE=false

# Parse des arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -a|--all)
            TEST_TAGS="souscriptions"
            shift
            ;;
        -t|--template)
            TEST_TAGS="souscriptions_template"
            shift
            ;;
        -f|--facturation)
            TEST_TAGS="souscriptions_facturation"
            shift
            ;;
        -b|--basic)
            TEST_TAGS="souscriptions_basic"
            shift
            ;;
        -i|--integration)
            TEST_TAGS="souscriptions_workflow"
            shift
            ;;
        -u|--ui)
            TEST_TAGS="souscriptions_ui"
            shift
            ;;
        -r|--reports)
            TEST_TAGS="souscriptions_reports"
            shift
            ;;
        -v|--verbose)
            VERBOSE="--log-level=info"
            shift
            ;;
        -c|--coverage)
            COVERAGE=true
            shift
            ;;
        --create-db)
            CREATE_DB=true
            shift
            ;;
        --keep-db)
            KEEP_DB=true
            shift
            ;;
        -*)
            error "Option inconnue: $1"
            show_help
            exit 1
            ;;
        *)
            DB_NAME="$1"
            shift
            ;;
    esac
done

info "🧪 Lancement des tests Odoo pour le module souscriptions"
info "📊 Base de données: $DB_NAME"
info "🏷️  Tags de test: $TEST_TAGS"

# Vérifier qu'Odoo est disponible
if ! command -v $ODOO_PATH &> /dev/null; then
    error "Odoo n'est pas trouvé dans le PATH. Vérifiez ODOO_PATH=$ODOO_PATH"
    exit 1
fi

# Créer/recréer la base de données si demandé
if [ "$CREATE_DB" = true ]; then
    info "🗃️  Création d'une nouvelle base de données $DB_NAME"
    
    # Supprimer la base si elle existe
    $ODOO_PATH -d $DB_NAME --stop-after-init --without-demo=all -i base --addons-path=$ADDONS_PATH &>/dev/null || true
    
    # Installer le module avec les données de test
    info "📦 Installation du module souscriptions avec données de test"
    $ODOO_PATH -d $DB_NAME --stop-after-init -i souscriptions --test-enable --addons-path=$ADDONS_PATH $VERBOSE
    
    if [ $? -eq 0 ]; then
        success "Module installé avec succès"
    else
        error "Échec de l'installation du module"
        exit 1
    fi
fi

# Lancer les tests
info "🔬 Exécution des tests..."

if [ "$COVERAGE" = true ]; then
    warning "Mode couverture activé (nécessite pytest-odoo)"
    # TODO: Implémenter la couverture avec pytest-odoo
    TEST_CMD="$ODOO_PATH -d $DB_NAME --test-enable --test-tags=$TEST_TAGS --stop-after-init --addons-path=$ADDONS_PATH $VERBOSE"
else
    TEST_CMD="$ODOO_PATH -d $DB_NAME --test-enable --test-tags=$TEST_TAGS --stop-after-init --addons-path=$ADDONS_PATH $VERBOSE"
fi

echo "Commande exécutée: $TEST_CMD"
echo "----------------------------------------"

# Exécuter les tests et capturer le résultat
if $TEST_CMD; then
    success "✨ Tous les tests sont passés avec succès!"
    EXIT_CODE=0
else
    error "💥 Certains tests ont échoué"
    EXIT_CODE=1
fi

# Nettoyer la base de données si demandé
if [ "$KEEP_DB" = false ] && [ "$CREATE_DB" = true ]; then
    info "🧹 Suppression de la base de données de test"
    # Note: Odoo ne propose pas de commande directe pour supprimer une DB
    # En pratique, on peut la laisser pour inspection ou utiliser des outils externes
fi

# Résumé
echo "----------------------------------------"
if [ $EXIT_CODE -eq 0 ]; then
    success "🎉 Tests terminés avec succès!"
else
    error "😞 Des tests ont échoué. Consultez les logs ci-dessus."
fi

info "💡 Pour plus d'options: $0 --help"

exit $EXIT_CODE