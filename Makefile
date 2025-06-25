# Makefile pour le module Odoo souscriptions
# Simplifie les commandes de test et de développement

# Variables
ODOO_PATH ?= odoo
ADDONS_PATH ?= /home/virgile/addons_odoo
DB_NAME ?= souscriptions_test
MODULE_NAME = souscriptions

# Couleurs
BLUE = \033[0;34m
GREEN = \033[0;32m
YELLOW = \033[1;33m
NC = \033[0m # No Color

.PHONY: help test test-all test-template test-facturation test-basic test-integration
.PHONY: install update demo clean lint coverage

# Aide par défaut
help:
	@echo "$(BLUE)🚀 Makefile pour le module Odoo souscriptions$(NC)"
	@echo ""
	@echo "$(YELLOW)Tests:$(NC)"
	@echo "  test              Lancer tous les tests"
	@echo "  test-template     Tests du template de facture uniquement"
	@echo "  test-facturation  Tests de facturation uniquement"
	@echo "  test-basic        Tests basiques uniquement"
	@echo "  test-workflow     Tests de workflow/intégration uniquement"
	@echo "  test-ui           Tests d'interface utilisateur uniquement"
	@echo "  test-reports      Tests de rapports uniquement"
	@echo "  test-verbose      Tests avec logs détaillés"
	@echo ""
	@echo "$(YELLOW)Développement:$(NC)"
	@echo "  install           Installer le module"
	@echo "  update            Mettre à jour le module"
	@echo "  demo              Lancer avec données de démo"
	@echo "  shell             Ouvrir un shell Odoo"
	@echo ""
	@echo "$(YELLOW)Maintenance:$(NC)"
	@echo "  clean             Nettoyer les fichiers temporaires"
	@echo "  lint              Linter le code (si flake8 disponible)"
	@echo "  format            Formater le code (si black disponible)"
	@echo ""
	@echo "$(YELLOW)Variables:$(NC)"
	@echo "  DB_NAME=$(DB_NAME)"
	@echo "  ODOO_PATH=$(ODOO_PATH)"
	@echo "  ADDONS_PATH=$(ADDONS_PATH)"

# Tests
test:
	@echo "$(BLUE)🧪 Lancement de tous les tests$(NC)"
	./run_tests.sh --create-db $(DB_NAME)

test-all: test

test-template:
	@echo "$(BLUE)🧪 Tests du template de facture$(NC)"
	./run_tests.sh --template $(DB_NAME)

test-facturation:
	@echo "$(BLUE)🧪 Tests de facturation$(NC)"
	./run_tests.sh --facturation $(DB_NAME)

test-basic:
	@echo "$(BLUE)🧪 Tests basiques$(NC)"
	./run_tests.sh --basic $(DB_NAME)

test-workflow:
	@echo "$(BLUE)🧪 Tests de workflow$(NC)"
	./run_tests.sh --integration $(DB_NAME)

test-ui:
	@echo "$(BLUE)🧪 Tests d'interface utilisateur$(NC)"
	./run_tests.sh --ui $(DB_NAME)

test-reports:
	@echo "$(BLUE)🧪 Tests de rapports$(NC)"
	./run_tests.sh --reports $(DB_NAME)

test-verbose:
	@echo "$(BLUE)🧪 Tests avec logs détaillés$(NC)"
	./run_tests.sh --verbose $(DB_NAME)

# Développement
install:
	@echo "$(BLUE)📦 Installation du module$(NC)"
	$(ODOO_PATH) -d $(DB_NAME) -i $(MODULE_NAME) --stop-after-init --addons-path=$(ADDONS_PATH)

update:
	@echo "$(BLUE)🔄 Mise à jour du module$(NC)"
	$(ODOO_PATH) -d $(DB_NAME) -u $(MODULE_NAME) --stop-after-init --addons-path=$(ADDONS_PATH)

demo:
	@echo "$(BLUE)🎭 Lancement avec données de démo$(NC)"
	$(ODOO_PATH) -d $(DB_NAME) --addons-path=$(ADDONS_PATH) --dev=reload,qweb,werkzeug,xml

shell:
	@echo "$(BLUE)🐚 Ouverture du shell Odoo$(NC)"
	$(ODOO_PATH) shell -d $(DB_NAME) --addons-path=$(ADDONS_PATH)

# Tests rapides pour développement
quick-test:
	@echo "$(BLUE)⚡ Tests rapides (sans recréer la DB)$(NC)"
	./run_tests.sh $(DB_NAME)

# Maintenance
clean:
	@echo "$(BLUE)🧹 Nettoyage des fichiers temporaires$(NC)"
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.log" -delete
	rm -f /tmp/facture_*.html
	@echo "$(GREEN)✅ Nettoyage terminé$(NC)"

lint:
	@echo "$(BLUE)🔍 Analyse du code avec flake8$(NC)"
	@if command -v flake8 >/dev/null 2>&1; then \
		flake8 models/ tests/ --max-line-length=120 --exclude=__pycache__; \
		echo "$(GREEN)✅ Linting terminé$(NC)"; \
	else \
		echo "$(YELLOW)⚠️  flake8 non disponible, installation: pip install flake8$(NC)"; \
	fi

format:
	@echo "$(BLUE)🎨 Formatage du code avec black$(NC)"
	@if command -v black >/dev/null 2>&1; then \
		black models/ tests/ --line-length=120; \
		echo "$(GREEN)✅ Formatage terminé$(NC)"; \
	else \
		echo "$(YELLOW)⚠️  black non disponible, installation: pip install black$(NC)"; \
	fi

# Tests avec couverture (si pytest-odoo disponible)
coverage:
	@echo "$(BLUE)📊 Tests avec couverture de code$(NC)"
	@if command -v pytest >/dev/null 2>&1; then \
		echo "$(YELLOW)TODO: Implémenter les tests pytest-odoo$(NC)"; \
	else \
		echo "$(YELLOW)⚠️  pytest non disponible$(NC)"; \
	fi

# Alias pratiques
t: test
tf: test-facturation
tt: test-template
tb: test-basic
tw: test-workflow
tu: test-ui
tr: test-reports
i: install
u: update
d: demo
s: shell
c: clean

# Validation complète avant commit
pre-commit: clean lint test
	@echo "$(GREEN)✅ Validation complète réussie, prêt pour commit!$(NC)"