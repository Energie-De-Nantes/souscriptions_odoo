# Deux sources de vérité (physique vs comptable) ; la marge vit dans la couche analytique

Le système assume **deux sources de vérité** partitionnées par domaine : **electricore** pour les
données *physiques/réseau* (périmètre, énergies, TURPE, accise — ré-interrogeables à tout moment par
`RSC` + mois) ; **Odoo** pour la *comptabilité* (prix, grilles, factures, ce qui est facturé).
Frontière par propriété de champ — **« référencer, pas recopier »** : Odoo ne stocke pas le coût
réseau, electricore ne stocke pas les prix.

**Concrètement pour les taxes** : les taxes **réglementées** (accise, CTA, TURPE) sont calculées et
versionnées par electricore (millésimes, références réglementaires) ; Odoo n'en maintient **aucun
taux** — il reçoit les montants et les restitue sur la facture. La **seule** taxe gérée dans Odoo est
la **TVA** (différenciée 5,5 % / 20 %), via `account.tax` + positions fiscales. Ceci **supersède**
AUDIT_REFONTE.md §4.1 (qui proposait de modéliser accise/CTA en `account.tax` côté Odoo).

**Présentation du TURPE** : visible sur la facture en **ligne informative non comptabilisée**
(« Dont TURPE fixe / variable… », `display_type='line_note'`) sous la part fixe et la part variable,
mais **pas refacturé ligne à ligne** — il est intégré aux prix fournisseur (abonnement, énergie).
Réconcilie l'exigence de visibilité (AUDIT §4.1) et le principe electricore (« le TURPE n'est pas
refacturé ligne à ligne »). Le même procédé (notes non comptabilisées) sert la lisibilité du détail.

## La Période n'est pas un instantané fidèle

Le flux Enedis est parfois incomplet : le·la *facturiste* doit saisir des estimations à la main et
appliquer des *gestes commerciaux* **avant** la génération de facture. La *Période* est donc un
**brouillon facturable éditable**, amorcé par electricore puis finalisé par le·la facturiste ; elle
historise ce qui est **facturé**, pas une copie du coût.

## La marge n'est pas câblée dans le transactionnel

Le contrôle de marge / de refacturation du TURPE vit dans la **couche analytique** (paquet non-core
du monorepo electricore, outils Marimo), qui lit electricore (coût) + Odoo (facturé) **à la demande**.
Pas de snapshot de coût parallèle dans Odoo.

## Raison

KISS : bonne couverture du process principal avec une infra maintenable, plutôt que pré-gérer chaque
cas limite. L'estimation de marge actuelle est grossière — la précision n'est pas un objectif du
chemin transactionnel, et les décisions de cas limites sont prises par des humains au moment voulu
(elles ne concernent pas electricore).

## Option écartée

Instantané physique fidèle + couche commerciale explicite portée par la Période (marge calculable en
transactionnel) : sur-ingénierie pour un gain non prioritaire, et incompatible avec la saisie
manuelle d'estimations quand le flux manque.
