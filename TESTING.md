# Guide de Test - Module Souscriptions

Ce guide suit les **standards Python unittest** et les **recommandations officielles Odoo**.

## 🎯 Approche recommandée

### 1. **Test Runner Python (Recommandé)**
```bash
# Lancer tous les tests
python test_runner.py

# Tests spécifiques
python test_runner.py basic
python test_runner.py template --verbose
python test_runner.py workflow --install

# Aide complète
python test_runner.py --help
```

### 2. **Commandes Odoo officielles**
```bash
# Tous les tests
odoo -d souscriptions_test --test-enable --test-tags souscriptions --stop-after-init -i souscriptions

# Tests spécifiques par tag
odoo -d test_db --test-enable --test-tags souscriptions_basic --stop-after-init
odoo -d test_db --test-enable --test-tags souscriptions_template --stop-after-init
```

### 3. **Python unittest discovery**
```bash
# Découverte automatique (exploration uniquement)
python -m unittest discover -s tests -p "test_*.py" -v

# Test spécifique
python -m unittest tests.test_basic.TestBasic.test_models_exist
```

## 📁 Structure des tests

```
tests/
├── __init__.py
├── common.py                   # Helpers unittest standard
├── test_basic.py              # unittest.TestCase basique
├── test_facturation.py        # unittest.TestCase facturation  
├── test_template.py           # unittest.TestCase template
├── test_workflow.py           # unittest.TestCase workflow
└── test_ui.py                 # unittest.TestCase interface
```

## 🏷️ Tags de test disponibles

| Tag | Description | Usage |
|-----|-------------|--------|
| `souscriptions` | Tous les tests | `python test_runner.py all` |
| `souscriptions_basic` | Tests basiques | `python test_runner.py basic` |
| `souscriptions_facturation` | Tests facturation | `python test_runner.py facturation` |
| `souscriptions_template` | Tests template | `python test_runner.py template` |
| `souscriptions_workflow` | Tests workflow | `python test_runner.py workflow` |
| `souscriptions_ui` | Tests interface | `python test_runner.py ui` |

## 🛠️ Outils disponibles

### Test Runner Python (⭐ Recommandé)
```bash
python test_runner.py --help           # Aide complète
python test_runner.py --list-tags      # Liste des tags
python test_runner.py --discover       # Discovery unittest
python test_runner.py --quick          # Tests rapides
```

### Makefile simplifié
```bash
make help                       # Aide
make test                       # Via test_runner.py
make test-odoo                  # Commande Odoo directe  
make test-unittest              # Discovery unittest
make install                    # Installer module
```

### Configuration unittest
- **`unittest.cfg`** : Configuration standard Python
- **Test discovery** : Automatique selon pattern `test_*.py`
- **Verbosity** : Logs détaillés par défaut

## 🎨 Bonnes pratiques

### Structure de test unittest standard
```python
import unittest
from odoo.tests.common import TransactionCase, tagged

@tagged('souscriptions_basic')
class TestBasic(TransactionCase):
    """Tests basiques suivant unittest standards."""
    
    def setUp(self):
        """Setup unittest standard."""
        super().setUp()
        # Préparation des données
    
    def test_something(self):
        """Test spécifique avec nomenclature unittest."""
        # Arrange
        # Act  
        # Assert avec unittest assertions
        self.assertEqual(actual, expected)
        self.assertTrue(condition)
        self.assertIn(item, container)
    
    def tearDown(self):
        """Cleanup unittest standard."""
        super().tearDown()
        # Nettoyage si nécessaire
```

### Assertions unittest recommandées
```python
# Égalité et comparaisons
self.assertEqual(a, b)
self.assertNotEqual(a, b)
self.assertGreater(a, b)
self.assertIn(item, container)

# Booléens et None
self.assertTrue(condition)
self.assertFalse(condition)
self.assertIsNone(value)
self.assertIsNotNone(value)

# Exceptions
with self.assertRaises(ValueError):
    risky_operation()

# Collections
self.assertCountEqual(list1, list2)  # Même éléments, ordre différent
```

### Organisation modulaire
- **Un fichier par domaine** : `test_facturation.py`, `test_template.py`
- **Helpers communs** : `common.py` avec mixins unittest
- **Données isolées** : Fixtures dans `setUp()` ou `setUpClass()`
- **Tags granulaires** : Pour exécution sélective

## 🚀 Intégration CI/CD

### GitHub Actions (exemple)
```yaml
- name: Run Odoo Tests
  run: |
    python test_runner.py all --verbose
    # ou
    odoo -d test_db --test-enable --test-tags souscriptions --stop-after-init
```

### Commandes recommandées pour CI
```bash
# Installation + tests complets
python test_runner.py all --install --verbose

# Tests rapides pour PR
python test_runner.py basic --quick

# Tests spécifiques selon changements
python test_runner.py template  # Si modification template
python test_runner.py facturation  # Si modification facturation
```

## 🔧 Intégration VS Code

### Configuration automatique
Les tests sont automatiquement configurés dans VS Code via:
- **`.vscode/settings.json`** : Configuration unittest et Python
- **`.vscode/launch.json`** : Profils de débogage
- **`.vscode/tasks.json`** : Tâches prédéfinies
- **`.env`** : Variables d'environnement

### Utilisation dans VS Code
```bash
# Interface graphique
- Ouvrir la vue "Test" (Ctrl+Shift+U)
- Tests auto-découverts dans le dossier tests/
- Lancer individuellement ou par groupe
- Debugging intégré

# Raccourcis clavier  
- Ctrl+; Ctrl+A : Lancer tous les tests
- Ctrl+; Ctrl+R : Relancer les derniers tests
- F5 : Déboguer le test en cours

# Panel Command (Ctrl+Shift+P)
- "Python: Run All Tests"
- "Python: Discover Tests" 
- "Tasks: Run Task" -> Odoo tests
```

### Tasks disponibles
- **"Odoo: Run All Tests"** (Ctrl+Shift+P -> Tasks)
- **"Odoo: Run Basic Tests"**
- **"Odoo: Quick Test"** 
- **"Odoo: Install Module"**

## 📚 Références

- [Python unittest](https://docs.python.org/3/library/unittest.html) - Documentation officielle
- [Odoo Testing](https://www.odoo.com/documentation/18.0/developer/reference/backend/testing.html) - Standards Odoo
- [Test Discovery](https://docs.python.org/3/library/unittest.html#test-discovery) - Découverte automatique
- [VS Code Python Testing](https://code.visualstudio.com/docs/python/testing) - Intégration VS Code

## 💡 Conseils

1. **Utilisez `test_runner.py`** pour le développement quotidien
2. **Commandes Odoo directes** pour scripts CI/CD
3. **unittest discovery** pour exploration et debug
4. **Tags granulaires** pour tests sélectifs lors du développement
5. **Assertions unittest** plutôt que `assert` Python basique