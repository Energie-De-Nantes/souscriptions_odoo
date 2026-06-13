# Odoo, système d'écriture transactionnel ; l'API electricore reste read-only vers Odoo

Le module Odoo est l'**unique système d'écriture** de la facturation (Périodes, factures,
paiements, grilles de prix). L'API electricore est un service de **calcul-et-renvoi** : elle
expose en lecture les *méta-périodes* du mois — quantités **non valorisées** par
`(RSC, mois calendaire)` : énergies par cadran, jours, puissance, montants TURPE, assiettes
accise/CTA — et **n'écrit jamais** dans Odoo. Odoo *tire* ces quantités, construit ses
*Périodes* typées, applique ses *grilles de prix*, génère la facture ; le·la *facturiste*
valide dans Odoo.

## Portée de l'invariant

« electricore n'écrit pas dans Odoo » porte sur l'**API / le flux automatique**, **pas sur
le dépôt de code** electricore. Les outils interactifs (Marimo, couche analytique) peuvent
**lire Odoo en read-only** et n'y écrire **que sous validation humaine explicite** — reprise
directe du principe d'electricore (ADR-0012).

## Options écartées

- **AUDIT_REFONTE.md, Option A** (electricore *upsert* `souscription.periode` dans Odoo) :
  viole le read-only-vers-Odoo (electricore ADR-0012) et recouple electricore au schéma Odoo
  (electricore ADR-0016).
- **Option B** (refonder l'addon sur `sale.order`) : écartée par l'intention « pas de devis,
  données métier hors module comptable ».

## Conséquences

- Le *rapprochement par RSC* migre dans Odoo (electricore ne lit plus `sale.order` pour le faire).
- L'ancien chemin notebook + write-back disparaît du **flux standard** de facturation.
- electricore doit exposer un endpoint de lecture des méta-périodes (GET en masse +
  POST recompute ciblé) — donnée qu'il calcule déjà (`ContexteMensuel.facturation_mensuelle`).
- electricore ADR-0012 reste **inchangé**.
