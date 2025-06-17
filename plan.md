# Plan de Restructuration Modulaire - Addon Souscriptions

## Contexte

Le projet addon Souscriptions est en phase exploratoire avec deux composants principaux :
- **Module Souscriptions** : Gestion des paramètres de facturation et remplacement du module abonnement d'Odoo
- **Module Métier** : Représentation des données Enedis dans Odoo

**Objectif** : Créer une version minimale du module souscriptions, avec les données métier gérées temporairement par un pont Python externe, tout en préparant une architecture permettant l'intégration future du module métier.

## Analyse des Dépendances Actuelles

### Composants Souscriptions Core
- `souscription.py` - Modèle principal de souscription
- `souscription_periode.py` - Périodes de facturation
- `account_move.py` - Extensions des factures
- `souscription_views.xml` - Vues principales
- `souscriptions_periode_views.xml` - Vues des périodes
- Données : `souscription_etat_data.xml`, `souscription_sequence.xml`, `produits_abonnement.xml`

### Composants Métier (Enedis)
- `metier_perimetre.py` - Données d'historique périmètre
- `metier_prestation.py` - Données de facturation services
- `metier_mesure_index.py` - Relevés de consommation
- Importeurs : `metier_*_importer.py`
- Vues : `metier_*.xml`

### Dépendances Identifiées

#### Dépendances Fortes (Computed Fields)
```python
# Dans souscription.py
historique_perimetre_ids = fields.One2many(compute='_compute_historique_perimetre')
prestations_ids = fields.One2many(compute='_compute_prestations')

@api.depends('pdl')
def _compute_historique_perimetre(self):
    # Recherche dans metier.perimetre par PDL

@api.depends('pdl') 
def _compute_prestations(self):
    # Recherche dans metier.prestation par PDL
```

#### Intégration UI
- Onglets "Historique" et "Prestations facturées" dans la vue souscription
- Références croisées dans les vues métier

#### Clé de Liaison
- **PDL (Point De Livraison)** : Clé métier reliant tous les composants

## Architecture Cible

### Structure Modulaire en 3 Modules

```
souscriptions_core/          # Version minimale autonome
├── models/
│   ├── souscription.py      # Sans computed fields métier
│   ├── souscription_periode.py
│   └── account_move.py
├── views/
│   └── souscription_views.xml  # Sans onglets métier
├── data/
│   ├── souscription_etat_data.xml
│   ├── souscription_sequence.xml
│   └── produits_abonnement.xml
└── __manifest__.py          # Dépendances : base, mail, contacts, account

souscriptions_metier/        # Module données Enedis (développement futur)
├── models/
│   ├── metier_perimetre.py
│   ├── metier_prestation.py
│   ├── metier_mesure_index.py
│   └── metier_*_importer.py
├── views/
│   └── metier_*.xml
└── __manifest__.py          # Dépendances : souscriptions_core

souscriptions_bridge/        # Module d'intégration (développement futur)
├── models/
│   └── souscription_metier_mixin.py  # Computed fields métier
├── views/
│   └── souscription_metier_views.xml # Onglets métier
└── __manifest__.py          # Dépendances : souscriptions_core, souscriptions_metier
```

## Plan de Migration

### Phase 1 : Préparation (1-2 jours)

#### Étape 1.1 : Extraction des Computed Fields Métier
Créer un mixin pour isoler la logique métier :

```python
# Nouveau fichier : models/souscription_metier_mixin.py
class SouscriptionMetierMixin(models.AbstractModel):
    _name = 'souscription.metier.mixin'
    
    historique_perimetre_ids = fields.One2many(
        'metier.perimetre', 
        compute='_compute_historique_perimetre',
        string="Historique périmètre"
    )
    
    prestations_ids = fields.One2many(
        'metier.prestation',
        compute='_compute_prestations', 
        string="Prestations facturées"
    )
    
    @api.depends('pdl')
    def _compute_historique_perimetre(self):
        for record in self:
            if record.pdl:
                record.historique_perimetre_ids = self.env['metier.perimetre'].search([
                    ('pdl', '=', record.pdl)
                ])
            else:
                record.historique_perimetre_ids = False
    
    @api.depends('pdl')
    def _compute_prestations(self):
        for record in self:
            if record.pdl:
                record.prestations_ids = self.env['metier.prestation'].search([
                    ('pdl', '=', record.pdl)
                ])
            else:
                record.prestations_ids = False
```

#### Étape 1.2 : Extraction des Vues Métier
Créer des vues séparées pour les onglets métier :

```xml
<!-- Nouveau fichier : views/souscription_metier_views.xml -->
<odoo>
    <record id="view_souscription_form_metier" model="ir.ui.view">
        <field name="name">souscription.form.metier</field>
        <field name="model">souscription</field>
        <field name="inherit_id" ref="souscriptions_core.view_souscription_form"/>
        <field name="arch" type="xml">
            <notebook position="inside">
                <page string="Historique" name="historique">
                    <field name="historique_perimetre_ids" readonly="1">
                        <!-- Configuration des colonnes historique -->
                    </field>
                </page>
                <page string="Prestations facturées" name="prestations">
                    <field name="prestations_ids" readonly="1">
                        <!-- Configuration des colonnes prestations -->
                    </field>
                </page>
            </notebook>
        </field>
    </record>
</odoo>
```

### Phase 2 : Version Minimale (2-3 jours)

#### Étape 2.1 : Nettoyage du Modèle Souscription
Retirer de `souscription.py` :
- Les computed fields métier (`historique_perimetre_ids`, `prestations_ids`)
- Les méthodes `_compute_historique_perimetre` et `_compute_prestations`
- Les imports des modèles métier

#### Étape 2.2 : Nettoyage des Vues
Retirer de `souscription_views.xml` :
- Les onglets "Historique" et "Prestations facturées"
- Les références aux champs métier

#### Étape 2.3 : API pour Pont Externe
Ajouter dans `souscription.py` des méthodes API pour le pont Python :

```python
class Souscription(models.Model):
    _name = 'souscription'
    # ... champs existants ...
    
    # === API POUR PONT EXTERNE ===
    
    @api.model
    def get_souscriptions_by_pdl(self, pdl_list):
        """Récupère les souscriptions par liste de PDL - API pour pont externe"""
        return self.search([('pdl', 'in', pdl_list)]).read([
            'name', 'pdl', 'partner_id', 'date_debut', 'date_fin',
            'puissance_souscrite', 'type_tarif', 'lisse', 'provision_mensuelle_kwh'
        ])
    
    def get_billing_periods(self, date_start=None, date_end=None):
        """Récupère les périodes de facturation pour cette souscription"""
        domain = [('souscription_id', '=', self.id)]
        if date_start:
            domain.append(('date_debut', '>=', date_start))
        if date_end:
            domain.append(('date_fin', '<=', date_end))
        
        periods = self.env['souscription.periode'].search(domain)
        return periods.read([
            'date_debut', 'date_fin', 'energie_kwh', 'provision_kwh',
            'turpe_fixe', 'turpe_variable', 'facture_id'
        ])
    
    @api.model
    def create_billing_period(self, vals):
        """Crée une période de facturation - API pour pont externe"""
        return self.env['souscription.periode'].create(vals)
    
    def update_consumption_data(self, period_data):
        """Met à jour les données de consommation - API pour pont externe"""
        for period_vals in period_data:
            period_id = period_vals.pop('id')
            period = self.env['souscription.periode'].browse(period_id)
            period.write(period_vals)
        return True
```

#### Étape 2.4 : Mise à Jour du Manifest
```python
# __manifest__.py - Version minimale
{
    "name": "Souscriptions Core",
    "version": "0.2.0",
    "depends": ["base", "mail", "contacts", "account"],
    "author": "Virgile Daugé",
    "category": "Energy",
    "license": "AGPL-3",
    "description": """
        Gestion des souscriptions électriques - Version minimale
        
        Module principal pour la gestion des contrats de fourniture d'électricité.
        Remplace le module abonnement standard d'Odoo qui n'est pas adapté 
        aux spécificités de la fourniture d'électricité.
        
        Fonctionnalités :
        - Gestion des contrats de souscription
        - Périodes de facturation mensuelles
        - Intégration avec la facturation Odoo
        - API pour intégration de données externes
    """,
    "installable": True,
    "application": True,
    "auto_install": False,
    
    "data": [
        "security/ir.model.access.csv",
        "data/souscription_sequence.xml",
        "data/souscription_etat_data.xml", 
        "data/produits_abonnement.xml",
        "views/souscription_views.xml",
        "views/souscriptions_periode_views.xml",
    ],
}
```

### Phase 3 : Développement Futur du Module Métier

#### Étape 3.1 : Création du Module souscriptions_metier
- Déplacer tous les modèles `metier_*` et leurs importeurs
- Créer les vues spécifiques aux données métier
- Manifest avec dépendance sur `souscriptions_core`

#### Étape 3.2 : Création du Module souscriptions_bridge
- Implémenter le mixin d'intégration
- Faire hériter `souscription` du mixin
- Ajouter les vues d'intégration

## Interface Pont Python Externe

### Structure des Données
Le pont externe devra interagir avec Odoo via les APIs définies :

```python
# Exemple d'utilisation du pont externe
import odoorpc

# Connexion Odoo
odoo = odoorpc.ODOO('localhost', port=8069)
odoo.login('database', 'user', 'password')

# Récupération des souscriptions par PDL
souscriptions = odoo.env['souscription'].get_souscriptions_by_pdl(['PDL123', 'PDL456'])

# Mise à jour des données de consommation
for sous in souscriptions:
    periods = odoo.env['souscription'].browse(sous['id']).get_billing_periods()
    # Traitement des données métier...
    # Mise à jour via update_consumption_data()
```

## Avantages de cette Architecture

1. **Autonomie** : Version minimale opérationnelle sans dépendances externes
2. **Flexibilité** : Pont externe temporaire avec APIs claires
3. **Évolutivité** : Architecture prête pour intégration future du module métier
4. **Développement parallèle** : Équipes peuvent travailler séparément
5. **Tests isolés** : Chaque module testable indépendamment
6. **Migration progressive** : Pas de rupture de l'existant

## Risques et Mitigation

### Risques Identifiés
1. **Perte de fonctionnalité temporaire** : Onglets métier non disponibles
2. **Complexité du pont externe** : Logique métier déportée
3. **Performance** : Appels API vs computed fields

### Mitigation
1. **Documentation claire** des APIs du pont externe
2. **Tests d'intégration** entre Odoo et pont externe  
3. **Monitoring** des performances des APIs
4. **Plan de rollback** vers version actuelle si nécessaire

## Timeline Estimé

- **Phase 1** : 1-2 jours (préparation et extraction)
- **Phase 2** : 2-3 jours (version minimale + APIs)
- **Développement pont externe** : En parallèle (équipe externe)
- **Phase 3** : Développement futur selon disponibilités

## Prochaines Étapes

1. Validation de ce plan avec l'équipe
2. Sauvegarde de l'état actuel (git branch)
3. Exécution de la Phase 1
4. Tests de la version minimale
5. Développement du pont externe
6. Mise en production de la version minimale