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

## Concept Central : Modèle Période de Facturation

### Le Rôle Stratégique des SouscriptionPeriode

Le modèle `SouscriptionPeriode` est le **cœur du système de facturation électrique**. Il résout le paradoxe entre données métier et processus comptable en servant de **couche de calcul intermédiaire**.

#### Architecture en 3 Couches
```
Données Métier → SouscriptionPeriode → Processus Comptable
(index, relevés)  (calculs, provisions)   (factures Odoo)
```

### Données Contenues dans une Période

#### Données de Consommation par Cadrans
Les **cadrans** sont des compteurs d'énergie qui ne comptent que sur certaines périodes :
- **HPH** : Heures Pleines saison Haute (hiver)
- **HPB** : Heures Pleines saison Basse (été) 
- **HCH** : Heures Creuses saison Haute (hiver)
- **HCB** : Heures Creuses saison Basse (été)
- **HP** : Heures Pleines (agrégation HPH + HPB)
- **HC** : Heures Creuses (agrégation HCH + HCB)
- **BASE** : Tarif unique (HPH + HPB + HCH + HCB)

#### Structure des Données Période
```python
# Consommations détaillées (pour calcul TURPE)
energie_hph_kwh = fields.Float('Énergie HPH (kWh)')
energie_hpb_kwh = fields.Float('Énergie HPB (kWh)') 
energie_hch_kwh = fields.Float('Énergie HCH (kWh)')
energie_hcb_kwh = fields.Float('Énergie HCB (kWh)')

# Consommations facturables (selon contrat)
energie_hp_kwh = fields.Float('Énergie HP (kWh)', compute='_compute_hp_hc')
energie_hc_kwh = fields.Float('Énergie HC (kWh)', compute='_compute_hp_hc')
energie_base_kwh = fields.Float('Énergie BASE (kWh)', compute='_compute_base')

# Provisions (lissage) - selon type de contrat
provision_hp_kwh = fields.Float('Provision HP (kWh)')
provision_hc_kwh = fields.Float('Provision HC (kWh)')
provision_base_kwh = fields.Float('Provision BASE (kWh)')

# TURPE (calculé sur tous les cadrans)
turpe_fixe = fields.Float('TURPE Fixe (€)')
turpe_variable = fields.Float('TURPE Variable (€)')  # Utilise HPH+HPB+HCH+HCB

# Métadonnées période
type_periode = fields.Selection([
    ('mensuelle', 'Mensuelle'),
    ('regularisation', 'Régularisation'),
    ('ajustement', 'Ajustement')
], default='mensuelle')
jours = fields.Integer('Nombre de jours', compute='_compute_jours')

# HISTORISATION : État de la souscription au moment de la création
type_tarif_periode = fields.Char('Type tarif (période)', readonly=True)
tarif_solidaire_periode = fields.Boolean('Tarif solidaire (période)', readonly=True)
lisse_periode = fields.Boolean('Lissé (période)', readonly=True)
puissance_souscrite_periode = fields.Char('Puissance souscrite (période)', readonly=True)
provision_mensuelle_kwh_periode = fields.Float('Provision mensuelle (période)', readonly=True)
```

#### Logique de Calcul
```python
@api.depends('energie_hph_kwh', 'energie_hpb_kwh', 'energie_hch_kwh', 'energie_hcb_kwh')
def _compute_hp_hc(self):
    for periode in self:
        periode.energie_hp_kwh = periode.energie_hph_kwh + periode.energie_hpb_kwh
        periode.energie_hc_kwh = periode.energie_hch_kwh + periode.energie_hcb_kwh

@api.depends('energie_hp_kwh', 'energie_hc_kwh')  
def _compute_base(self):
    for periode in self:
        periode.energie_base_kwh = periode.energie_hp_kwh + periode.energie_hc_kwh

# Gestion des provisions selon type de contrat
@api.depends('souscription_id.type_tarif', 'souscription_id.lisse')
def _compute_provisions(self):
    for periode in self:
        if periode.souscription_id.lisse:
            # Provisions fixes pour lissage
            if periode.souscription_id.type_tarif == 'base':
                periode.provision_base_kwh = periode.souscription_id.provision_mensuelle_base_kwh
            else:  # HP/HC
                periode.provision_hp_kwh = periode.souscription_id.provision_mensuelle_hp_kwh
                periode.provision_hc_kwh = periode.souscription_id.provision_mensuelle_hc_kwh
        else:
            # Provisions = consommations réelles
            periode.provision_hp_kwh = periode.energie_hp_kwh
            periode.provision_hc_kwh = periode.energie_hc_kwh
            periode.provision_base_kwh = periode.energie_base_kwh
```

### Processus de Régularisation des Lissés

#### Principe des Contrats Lissés
Les clients paient un **montant fixe mensuel** pour étaler les coûts de l'hiver sur toute l'année, au lieu de payer leur consommation réelle chaque mois.

#### Mécanisme via les Périodes
```python
# Facturation mensuelle lissée
if souscription.lisse:
    periode.provision_kwh = souscription.provision_mensuelle_kwh  # Fixe
    periode._fix_provision = True
else:
    periode.provision_kwh = periode.energie_kwh  # Réelle
```

#### Processus de Régularisation
1. **Accumulation** : Chaque période garde la trace :
   - `energie_kwh` : Consommation réelle du mois
   - `provision_kwh` : Énergie facturée (fixe pour lissés)

2. **Calcul d'écart** : À la fin de l'année
   ```python
   total_consomme = sum(periode.energie_kwh for periode in periodes_annee)
   total_facture = sum(periode.provision_kwh for periode in periodes_annee)
   ecart_regularisation = total_consomme - total_facture
   ```

3. **Période de régularisation** : Création d'une période spéciale
   - `energie_kwh = 0` (pas de nouvelle consommation)
   - `provision_kwh = ecart_regularisation` (positif ou négatif)

#### Historisation Automatique des Paramètres

#### Principe d'Historisation
Chaque période **capture automatiquement l'état de la souscription** au moment de sa création :

```python
# À la création d'une période, copie automatique de :
type_tarif_periode = "Heures Pleines / Heures Creuses"  # État au moment T
tarif_solidaire_periode = False                         # État au moment T
puissance_souscrite_periode = "9 kVA"                   # État au moment T
lisse_periode = True                                     # État au moment T
```

#### Cas d'Usage d'Historisation
1. **Changement de puissance** : Client passe de 6 à 9 kVA en cours d'année
   - Périodes jan-mars : `puissance_souscrite_periode = "6 kVA"`
   - Périodes avr-déc : `puissance_souscrite_periode = "9 kVA"`

2. **Activation tarif solidaire** : Client devient éligible en cours d'année
   - Périodes jan-juin : `tarif_solidaire_periode = False`
   - Périodes juil-déc : `tarif_solidaire_periode = True`

3. **Changement type tarif** : Passage Base → HP/HC
   - Anciennes périodes : `type_tarif_periode = "Base"`
   - Nouvelles périodes : `type_tarif_periode = "Heures Pleines / Heures Creuses"`

#### Avantages de l'Historisation
- **Audit comptable** : Justification des calculs de facturation
- **Conformité réglementaire** : Traçabilité des changements tarifaires
- **Génération PDF factures** : Affichage des paramètres corrects selon la période
- **Régularisations précises** : Calculs basés sur les bons paramètres historiques

### Avantages du Modèle Période
- **Historique complet** : Toutes les données de calcul sont conservées
- **Historisation automatique** : État de la souscription figé à chaque période
- **Audit facile** : Traçabilité de chaque facturation avec paramètres exacts
- **Flexibilité** : Possibilité d'ajuster les calculs sans toucher aux factures
- **Régularisation simplifiée** : Données accumulées prêtes pour calcul d'écart

### Point d'Alimentation Flexible

#### Aujourd'hui : Alimentation Externe
```python
# Pont Python → API Odoo
periode_vals = {
    'energie_kwh': calcul_consommation_depuis_index(),
    'turpe_fixe': calcul_turpe_fixe(),
    'turpe_variable': calcul_turpe_variable(),
    'provision_kwh': calcul_provision_selon_contrat()
}
periode.write(periode_vals)
```

#### Demain : Intégration Métier
```python
# Computed depuis données métier
@api.depends('index_debut_id', 'index_fin_id')
def _compute_energie_kwh(self):
    for periode in self:
        if periode.index_debut_id and periode.index_fin_id:
            periode.energie_kwh = periode.index_fin_id.valeur - periode.index_debut_id.valeur

# Ou références directes
index_debut_id = fields.Many2one('metier.mesure.index')
index_fin_id = fields.Many2one('metier.mesure.index')
```

### Séparation des Responsabilités

#### SouscriptionPeriode : Calculs Métier
- Calcul de consommation depuis les index
- Gestion des provisions lissées
- Calcul des coûts réseau (TURPE)
- Régularisation des écarts

#### Processus Comptable : Génération Factures
- Création des factures Odoo depuis **données période + données souscription**
- Application des produits selon puissance souscrite et formule tarifaire
- Génération des lignes comptables
- **Processus standard Odoo, pas logique métier**

#### Données Nécessaires pour Génération Facture
```python
# Depuis SouscriptionPeriode
- provision_hp_kwh, provision_hc_kwh, provision_base_kwh (quantités à facturer)
- turpe_fixe, turpe_variable (montants TURPE)
- type_periode (mensuelle, régularisation, ajustement)

# Depuis Souscription  
- puissance_souscrite (détermine le produit abonnement)
- type_tarif (Base/HP-HC - détermine les produits énergie)
- tarif_solidaire (prix spéciaux)
- partner_id, pdl (données facture)
```

## Relations et Cardinalités entre Modèles

### Structure Relationnelle
```
Souscription (1) ←→ (n) SouscriptionPeriode (1) ←→ (0..1) AccountMove
     ↓                        ↓                           ↓
  Contrat              Données calculs              Facture comptable
(paramètres)          (consommations/provisions)      (document)
```

### Cardinalités Détaillées

#### Souscription → SouscriptionPeriode (1:n)
- **Une souscription** a **plusieurs périodes** (généralement mensuelle)
- Relation : `periode_ids = fields.One2many('souscription.periode', 'souscription_id')`
- Contrainte : Périodes non chevauchantes pour une même souscription

#### SouscriptionPeriode → AccountMove (1:0..1)
- **Une période** peut avoir **zéro ou une facture**
- Relation : `facture_id = fields.Many2one('account.move')`
- **Pas toujours 1:1** car :
  - Périodes créées avant facturation
  - Périodes de régularisation peuvent ne pas générer de facture
  - Possibilité d'annulation/refacturation

#### Types de Périodes et Facturation

##### Périodes Mensuelles (`type_periode='mensuelle'`)
- **Cardinalité** : 1 période → 1 facture (normale)
- **Données** : Consommations du mois + provisions selon contrat
- **Génération** : Automatique mensuelle

##### Périodes de Régularisation (`type_periode='regularisation'`)
- **Cardinalité** : 1 période → 1 facture (avoir/facture complémentaire)
- **Données** : Écarts accumulés sur l'année pour lissés
- **Génération** : Manuelle ou annuelle automatique

##### Périodes d'Ajustement (`type_periode='ajustement'`)
- **Cardinalité** : 1 période → 0..1 facture (selon besoin)
- **Données** : Corrections ponctuelles
- **Génération** : Manuelle uniquement

#### Lien Facture ↔ Période
```python
# account_move.py - Lien uni-directionnel
periode_id = fields.Many2one('souscription.periode')  # Facture pointe vers période

# Usage : PDF facture récupère contexte depuis période
def get_invoice_context(self):
    return {
        'consommation_reelle': self.periode_id.energie_kwh,
        'provision_facturee': self.periode_id.provision_kwh,
        'type_facturation': 'Lissé' if self.periode_id.lisse else 'Réel'
    }
```

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