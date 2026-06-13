# Lien Période ↔ Facture : une seule source, côté facture

Une *Période* et sa *Facture* étaient reliées par **deux champs parallèles indépendants** :
`account.move.periode_id` (la facture pointe sa période) et `souscription.periode.facture_id`
(M2o distinct, écrit à la main par le workflow de facturation). Rien ne garantissait leur
cohérence, et en pratique les données démo ne peuplaient que `periode_id` — laissant
`facture_id` (donc `souscription.facture_ids`, donc le bloc « Factures récentes » du portail)
**vide pour tous les contrats démo**.

**Décision** : `account.move.periode_id` est la **seule source de vérité** du lien. Le champ
`souscription.periode.facture_id` devient **calculé/stocké, inverse** de `periode_id` ; on
**supprime** son écriture manuelle dans le workflow (`_creer_facture_periode` crée déjà le
`account.move` avec `periode_id`). Le garde-anti-doublon (`periode_ids.filtered(lambda p: not
p.facture_id)`) et `souscription.facture_ids` (mapping de `facture_id`) continuent de fonctionner
sans changement d'appelant.

## « Facturée » vs « émise »

`facture_id` est posé **dès qu'une facture existe** (brouillon inclus) — c'est ce qui préserve
l'anti-doublon : on ne re-facture pas une période qui a déjà un `account.move`. Mais le *Portail*
ne montre une *Période* que si sa *Facture* est **émise** (`state == 'posted'`). Les deux notions
sont distinctes et toutes deux nécessaires : l'une protège la facturation, l'autre protège
l'usager d'un brouillon non finalisé. Voir le terme **Facture** dans `CONTEXT.md`.

## Conséquences

- Migration : recalcul de `facture_id` sur l'existant (dérivé de `periode_id`).
- Le workflow ne doit plus écrire `periode.facture_id` (champ calculé).
- Les factures démo doivent porter `periode_id` **et** être **postées** pour s'afficher au portail
  (notamment celles ajoutées pour le contrat vitrine S0005).

## Raison

KISS : un seul lien à maintenir, dans le sens naturel (« une facture facture une période »), au
lieu de deux champs à synchroniser. C'est aussi le seul sens déjà peuplé partout (création réelle
+ démo), donc le moins coûteux à fiabiliser.

## Options écartées

- **Garder `facture_id` stocké éditable et le peupler partout** : maintient deux liens
  désynchronisables ; charge de cohérence permanente.
- **Tout relier via la Période** (avoirs, réguls compris) : détourne le concept *Période*
  (brouillon mensuel amorcé par electricore) et ne règle pas les documents sans période.

## Hors périmètre (follow-up)

L'affichage des **avoirs** (via `reversed_entry_id`), des **périodes de régularisation** couvrant
d'autres périodes, et le **visuel croisé** « telle régul régularise telles périodes/factures »
sont une évolution distincte, à concevoir avec son propre ADR.
