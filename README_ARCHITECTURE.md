# Architecture — Module Souscriptions

## Vue d'ensemble

`souscriptions_odoo` est un addon **Odoo 19** de gestion des contrats de fourniture
d'électricité. Il remplace le module d'abonnement standard d'Odoo, inadapté aux
spécificités de l'électricité (changements de prix en cours de contrat, facturation
au prix historique, lissage avec régularisation).

## Répartition des responsabilités

Les calculs métier sont délégués à
[electricore](https://github.com/Energie-De-Nantes/electricore) (API REST déployée) :

| Responsabilité | Système |
|---|---|
| Ingestion des flux Enedis (C15, R151, F15…) | electricore |
| Calculs métier : périmètre, énergies par cadran, TURPE, accise | electricore |
| Archivage des périodes de facturation raffinées | Odoo |
| Règles tarifaires (grilles de prix) | Odoo |
| Facturation, taxes, comptabilité légale, paiements | Odoo |
| Portail usager·ère, workflow de raccordement | Odoo |

electricore alimente les périodes de facturation via son API ; Odoo ne contient
aucun import de données Enedis (l'ancien module « Métier » à base de Parquet /
pandas a été retiré).

## Structure

```
souscriptions_odoo/
├── models/
│   ├── core/              # souscription, période, grille de prix, account.move
│   └── raccordement/      # workflow kanban de demande de raccordement
├── controllers/           # portail usager·ère
├── views/, reports/       # vues XML et rapports QWeb
├── data/                  # données de configuration (prod)
├── demo/                  # données de démonstration uniquement
├── security/              # droits d'accès et règles
└── tests/                 # suite de tests (TransactionCase / HttpCase)
```

## Installation

```bash
odoo -d votre_base -i souscriptions_odoo
```

## Tests

```bash
odoo -d test_db -i souscriptions_odoo --test-enable --test-tags /souscriptions_odoo --stop-after-init
```

## Suite de la refonte

Le plan complet est dans `AUDIT_REFONTE.md` et suivi dans le jalon GitHub
« Refonte Odoo 19 » (issues #10–#22).
