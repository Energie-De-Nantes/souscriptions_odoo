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

Le module cible **Odoo 19**. La méthode recommandée et reproductible (identique
à la CI) passe par Docker : aucune installation locale d'Odoo n'est requise.

### Méthode recommandée : Docker (comme la CI)

```bash
cd <racine du dépôt>

# 1. Démarrer PostgreSQL sur un réseau dédié
docker network create odoo-test
docker run -d --name souscriptions-pg --network odoo-test \
  -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=odoo -e POSTGRES_DB=postgres postgres:15

# 2. Installer le module et lancer toute la suite (base jetable)
docker run --rm --network odoo-test \
  -e HOST=souscriptions-pg -e USER=odoo -e PASSWORD=odoo \
  -v "$PWD:/mnt/extra-addons/souscriptions_odoo:ro" \
  odoo:19 odoo \
    --addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons \
    -d test_db -i souscriptions_odoo \
    --test-enable --test-tags /souscriptions_odoo \
    --stop-after-init --log-level=test

# 3. Nettoyage éventuel
docker rm -f souscriptions-pg && docker network rm odoo-test
```

La ligne de résultat à surveiller : `X failed, Y error(s) of N tests`.
Le code de sortie est non nul si un test échoue (utile en script/CI).

> ⚠️ **Piège** : passer l'hôte de la base via la variable d'environnement
> `HOST`, **pas** via `--db_host`. L'entrypoint de l'image officielle `odoo`
> reconstruit `--db_host` à partir de `HOST` (valeur par défaut `db`) et l'ajoute
> *après* la commande, écrasant tout `--db_host` fourni en ligne de commande.

### Si une instance Odoo 19 est disponible localement

```bash
# Toute la suite du module
odoo -d test_db -i souscriptions_odoo --test-enable --test-tags /souscriptions_odoo --stop-after-init

# Une suite précise (par tag de classe)
odoo -d test_db -i souscriptions_odoo --test-enable --test-tags souscriptions_facturation --stop-after-init

# Une classe précise
odoo -d test_db -u souscriptions_odoo --test-enable --test-tags :TestGrillePrix --stop-after-init
```

### Sélection des tests (`--test-tags`)

| Cible | Tag |
|---|---|
| Tous les tests du module | `/souscriptions_odoo` |
| Facturation | `souscriptions_facturation` |
| Grilles de prix | `souscriptions` (classe `TestGrillePrix`) |
| Sécurité / droits d'accès | `souscriptions_security` |
| Portail | `portal` |
| Une classe nommée | `:NomDeClasse` |

### Intégration continue

Le workflow [`.github/workflows/tests.yml`](../.github/workflows/tests.yml)
exécute automatiquement cette suite (PostgreSQL 15 + `odoo:19`) à chaque push
sur `main` et à chaque pull request. Le badge d'état figure dans le README.

### Suites actives

Les fichiers réellement exécutés sont ceux importés dans
[`__init__.py`](__init__.py) : `test_basic`, `test_souscription`,
`test_facturation`, `test_grille_prix`, `test_integration`, `test_portal`,
`test_raccordement`, `test_security` (91 tests au total).

Les fichiers `test_ui.py`, `test_workflow.py` et `test_invoice_template.py`
existent mais ne sont pas encore réactivés dans `__init__.py` ; les y rebrancher
demande d'abord de vérifier leur compatibilité avec le modèle actuel.

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

### Utilisation des helpers communs
```python
from .common import SouscriptionsTestMixin, build_grille_lignes

class TestX(SouscriptionsTestMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()  # partenaires, état, grille tarifée, souscriptions
```

> Les `env.ref(...)` doivent utiliser le préfixe du module technique
> `souscriptions_odoo.` (ex. `souscriptions_odoo.souscriptions_product_energie_base`).

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
- ✅ Types de tarifs (Base, HP/HC, Solidaire)
- ✅ Grilles par date, prix par puissance, prorata exact
- ✅ Sécurité / droits d'accès (groupes user/manager)
- ✅ Portail usager·ère
- ✅ Gestion d'erreurs

### À ajouter :
- [ ] Tests de performance
- [ ] Upsert idempotent des périodes (intégration electricore)
- [ ] Régularisation des contrats lissés
- [ ] Réactivation de `test_ui` / `test_workflow` / `test_invoice_template`

## 🚨 Dépannage

### Tests qui échouent
1. Vérifier que le module est bien installé
2. Vérifier les dépendances (produits, grilles prix)
3. Consulter les logs avec `--verbose`
4. Vérifier les fixtures dans `tests/data/`

### Base de données
```bash
# Repartir d'une base propre : supprimer la base de test
docker exec souscriptions-pg psql -U odoo -c "DROP DATABASE IF EXISTS test_db;"

# Inspecter la base après un run (omettre --stop-after-init pour garder l'instance)
docker exec -it souscriptions-pg psql -U odoo -d test_db
```

### Problèmes courants
- **Modèles non trouvés** : Module non installé ou mal configuré
- **Fixtures manquantes** : Fichier XML mal formé ou non chargé
- **Template errors** : Vérifier la syntaxe QWeb et les champs

## 📚 Ressources

- [Documentation tests Odoo](https://www.odoo.com/documentation/19.0/developer/reference/backend/testing.html)
- [TransactionCase API](https://www.odoo.com/documentation/19.0/developer/reference/backend/testing.html#odoo.tests.common.TransactionCase)
- [Tags de test](https://www.odoo.com/documentation/19.0/developer/reference/backend/testing.html#test-selection)