# Tests du module Souscriptions

Ce répertoire contient tous les tests automatisés du module souscriptions, utilisant le framework de test intégré d'Odoo.

## 📁 Structure

```
tests/
├── README.md                   # Cette documentation
├── __init__.py                 # Initialisation des tests
├── common.py                   # Helpers et mixins communs
├── data/
│   └── test_fixtures.xml       # Données de test réutilisables
├── test_basic.py               # Tests basiques des modèles (TransactionCase)
├── test_facturation.py         # Tests de facturation (TransactionCase)
├── test_grille_prix.py         # Tests des grilles de prix (TransactionCase)
├── test_integration.py         # Tests d'intégration legacy
├── test_invoice_template.py    # Tests du template de facture (TransactionCase)
├── test_souscription.py        # Tests des souscriptions (TransactionCase)
├── test_ui.py                  # Tests d'interface utilisateur (HttpCase)
├── test_portal.py              # Tests du portal client (HttpCase)
└── test_workflow.py            # Tests de workflow complexes (SavepointCase)
```

## 🚀 Lancement des tests

### Commande Odoo directe

```bash
# Tests avec tags
odoo -d test_db --test-enable --test-tags souscriptions --stop-after-init

# Tests spécifiques
odoo -d test_db --test-enable --test-tags TestInvoiceTemplate --stop-after-init
```

## 🧪 Types de tests

### Tests basiques (`test_basic.py`) - TransactionCase
- Import des modèles
- Existence des modèles principaux
- Tests de base
- Tag: `souscriptions_basic`

### Tests de facturation (`test_facturation.py`) - TransactionCase
- Création de périodes de facturation
- Génération de factures avec TURPE
- Tests Base et HP/HC
- Calculs des montants
- Gestion des erreurs
- Tag: `souscriptions_facturation`

### Tests du template (`test_invoice_template.py`) - TransactionCase
- Rendu HTML du template personnalisé
- Affichage des informations souscription
- Notes TURPE correctes
- Sections Abonnement/Énergie
- Support tarif solidaire
- Fallback pour factures non-énergie
- Tag: `souscriptions_template`

### Tests de workflow (`test_workflow.py`) - SavepointCase
- Workflows complets avec savepoints
- Scénarios de migration de tarifs
- Régularisation de contrats lissés
- Gestion d'erreurs avec rollback
- Tests de performance batch
- Tag: `souscriptions_workflow`

### Tests d'interface (`test_ui.py`) - HttpCase
- Vues et formulaires web
- Navigation dans l'interface
- Génération de rapports PDF
- Prévisualisation HTML
- Tag: `souscriptions_ui`, `souscriptions_reports`

### Tests du portal (`test_portal.py`) - HttpCase
- Authentification et sécurité portal
- Navigation et interface usager·ère
- Affichage adaptatif Base vs HP/HC
- Calculs et totaux automatiques
- Intégration avec le système Odoo
- Gestion des cas limites
- Tag: `portal`, `portal_integration`

### Helpers communs (`common.py`)
- `SouscriptionsTestMixin`: Données et helpers partagés
- `SouscriptionsTestCase`: Classe de base avec mixin
- `SouscriptionsFormTestCase`: Spécialisée pour les formulaires

## 📊 Données de test

### Fixtures (`tests/data/test_fixtures.xml`)
- États de facturation de test
- Clients de test (particuliers, entreprise, solidaire)
- Souscriptions avec différents profils
- Périodes avec données réalistes

### Utilisation des fixtures
```python
def setUp(self):
    super().setUp()
    # Les fixtures sont automatiquement chargées
    self.souscription_test = self.env.ref('souscriptions.souscription_test_base')
```

## 🎯 Meilleures pratiques

### Structure des tests
```python
@tagged('souscriptions', 'post_install', '-at_install')
class TestMonModule(TransactionCase):
    
    def setUp(self):
        super().setUp()
        # Setup des données communes
    
    def test_feature_specific(self):
        """Description claire du test"""
        # Arrange
        # Act  
        # Assert
```

### Tags recommandés
- `souscriptions` : Tag principal du module
- `post_install` : Tests après installation
- `-at_install` : Ne pas lancer à l'installation

### Assertions courantes
```python
# Existence et égalité
self.assertTrue(facture.is_facture_energie)
self.assertEqual(facture.souscription_id, souscription)

# Contenu HTML
self.assertIn('Facture d\'Électricité', html_content)

# Exceptions
with self.assertRaises(UserError):
    method_that_should_fail()

# Collections
self.assertGreater(len(lines), 0)
lines = records.filtered(lambda r: r.field == value)
```

## 🔧 Configuration

### Variables d'environnement
- `ODOO_PATH` : Chemin vers l'exécutable Odoo
- `ADDONS_PATH` : Chemin vers les addons

### Base de données de test
- Par défaut : `souscriptions_test`
- Recréée automatiquement avec `--create-db`
- Conservée pour inspection avec `--keep-db`

## 📈 Couverture de test

### Tests actuels couvrent :
- ✅ Modèles de base (souscription, période, grille prix)
- ✅ Génération de factures avec TURPE
- ✅ Template de facture personnalisé 
- ✅ Types de tarifs (Base, HP/HC, Solidaire)
- ✅ Calculs et montants
- ✅ Gestion d'erreurs

### À ajouter :
- [ ] Tests de performance
- [ ] Tests de migration
- [ ] Tests d'API REST
- [ ] Tests de sécurité
- [ ] Tests de workflow métier complet

## 🚨 Dépannage

### Tests qui échouent
1. Vérifier que le module est bien installé
2. Vérifier les dépendances (produits, grilles prix)
3. Consulter les logs avec `--verbose`
4. Vérifier les fixtures dans `tests/data/`

### Base de données
```bash
# Recréer la base de test
make test  # Recrée automatiquement

# Shell de debug
make shell
```

### Problèmes courants
- **Modèles non trouvés** : Module non installé ou mal configuré
- **Fixtures manquantes** : Fichier XML mal formé ou non chargé
- **Template errors** : Vérifier la syntaxe QWeb et les champs

## 📚 Ressources

- [Documentation tests Odoo](https://www.odoo.com/documentation/18.0/developer/reference/backend/testing.html)
- [TransactionCase API](https://www.odoo.com/documentation/18.0/developer/reference/backend/testing.html#odoo.tests.common.TransactionCase)
- [Tags de test](https://www.odoo.com/documentation/18.0/developer/reference/backend/testing.html#test-selection)