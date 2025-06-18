# Données de démonstration - Souscriptions

## Installation avec données de démo

```bash
# Base propre avec données de démo
odoo -d souscriptions_demo --addons-path=/home/virgile/addons_odoo,/usr/lib/python3/dist-packages/odoo/addons -i souscriptions --load-language=fr_FR --stop-after-init

# Tests uniquement
odoo -d souscriptions_test --addons-path=/home/virgile/addons_odoo,/usr/lib/python3/dist-packages/odoo/addons --test-tags souscriptions --stop-after-init
```

## Jeux de données créés

### 1. Clients de démonstration (`demo/souscriptions_demo.xml`)

- **Marie Dupont** - Particulier BASE 6 kVA, lissé
- **Jean Martin** - Particulier HP/HC 9 kVA, lissé  
- **Boulangerie Bio du Coin** - PRO 12 kVA, majoration 15%
- **Sophie Leroy** - Solidaire 3 kVA, chèque énergie

### 2. Souscriptions types

- **BASE** : Particulier et PRO
- **HP/HC** : Avec répartition 70% HP / 30% HC
- **Solidaire** : Réduction tarifaire
- **Lissage** : Provisions mensuelles fixes

### 3. Périodes avec consommations réalistes

- Données d'énergie variées selon saison
- TURPE calculé sur tous les cadrans
- Historique sur plusieurs mois

### 4. Grille de prix 2024

Prix réalistes basés sur tarifs réglementés :
- **Énergie BASE** : 0.2276 €/kWh
- **Énergie HP** : 0.2516 €/kWh  
- **Énergie HC** : 0.2032 €/kWh

## Utilisation pour les tests

Les tests utilisent les données créées automatiquement lors de leur exécution.
Fichier dédié : `tests/data/test_data.xml` (non chargé en production).

## Workflow de démonstration

1. **Consultation** des souscriptions créées
2. **Génération de factures** via `creer_factures()`
3. **Visualisation** des périodes et consommations
4. **Export PDF** des contrats
5. **Tests API** pour pont externe