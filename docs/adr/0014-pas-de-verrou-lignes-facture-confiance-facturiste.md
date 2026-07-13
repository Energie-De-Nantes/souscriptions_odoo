# Pas de verrou des lignes de facture : confiance au·à la facturiste, dérive Facture↔Période tolérée

[ADR-0007](0007-snapshot-periode-type-verrou-facturation.md) a figé la *Période* à la facturation
(le modèle `souscription.periode` devient lecture seule dès qu'une *Facture* le référence). Reste la
question **distincte** (issue #35) de l'éditabilité de la *Facture* elle-même (`account.move` /
`account.move.line`) : faut-il **verrouiller** les lignes générées depuis la Période pour qu'elles ne
soient pas retouchées à la main ? Cet ADR tranche : **non**.

## Décision

1. **Aucun verrou des lignes de facture.** `account.move.line` n'est **ni étendu** d'un drapeau de
   provenance (`généré-période`) **ni gardé** par un `write()` surchargé. Le **brouillon** de facture
   reste librement éditable par le·la *facturiste* — ajout de lignes, *gestes commerciaux*,
   corrections. L'**émission** (`posted`) la fige, mais c'est déjà acquis (immutabilité légale
   anti-fraude), pas un mécanisme du module.

2. **La Période est la source analytique ; la Facture en est une projection.** Les champs **typés**
   de la Période ([#14](https://github.com/Energie-De-Nantes/souscriptions_odoo/issues/14)), alimentés
   par electricore ([#18](https://github.com/Energie-De-Nantes/souscriptions_odoo/issues/18)), sont lus
   et **agrégés directement** par l'analytique. L'analytique **ne reconstruit jamais** les faits de
   facturation depuis les lignes (`account.move.line → product_id → categ_id → name`)
   ([ADR-0002](0002-deux-sources-de-verite-marge-en-analytique.md)).

3. **Dérive tolérée et bornée.** Une retouche manuelle d'une ligne vit sur la **Facture**, pas sur la
   **Période** : la Facture peut **diverger** ; la Période reste correcte-à-la-génération. La dérive
   vaut la **somme des éditions manuelles** — un *budget d'erreur humaine* assumé. Elle est
   **directionnelle** : une correction sur facture sous-représente dans l'analytique exactement les cas
   où la Période était fausse. Conséquence : la **réconciliation/audit par contrat lit la Facture**,
   l'analytique **générale** lit la Période.

4. **Geste commercial au jugement du·de la facturiste.** Réalisé soit comme **ligne de remise dédiée**,
   soit comme **édition directe** d'une ligne (ex. jours facturés réduits). Aucune des deux formes
   n'est imposée (KISS) : `CONTEXT.md` conserve l'exemple « jours facturés réduits ».

## Conséquences

- **Le verrou de la Période ([ADR-0007](0007-snapshot-periode-type-verrou-facturation.md)) reste le
  seul verrou.** Il vit sur un modèle **propre** (`souscription.periode`), peu coûteux à garder ; il
  protège la **source**, ce qui suffit.
- **Pas d'override de `write()` sur un modèle cœur très sollicité.** `account.move.line` est la table la
  plus chaude d'Odoo et l'ORM la réécrit en permanence (taxes, soldes, lettrage, distribution
  analytique). On évite de **combattre les recomputes** et la **dette de re-validation à chaque montée
  de version** Odoo.
- **L'analytique fine/par-contrat doit lire la Facture** (la projection légale réellement émise), pas
  la Période. C'est le prix assumé de la dérive.

## Options écartées

- **Drapeau de provenance + `write()`-guard sur `account.move.line`** (lecture « dure » de #35) :
  protège un couplage (Facture == Période) dont l'analytique **n'a pas besoin** — elle lit la Période.
  Coût : garde fragile sur la table la plus chaude d'Odoo, risque de casser les recomputes ORM, dette
  d'upgrade. Le gain (zéro dérive) ne vaut pas ce coût pour de l'analytique générale.
- **Inférer la provenance via `product_id` / catégorie** : reconstruit **exactement** le parcours
  `ligne → produit → catégorie` que la Période typée **supprime** (cf. l'ancien lecteur
  `lignes_factures_du_mois` côté electricore). Rebâtir cette friction dans le verrou serait un comble.
- **Verrou à l'émission seulement** : sans objet — `posted` est déjà immuable (anti-fraude) ; il n'y a
  rien à ajouter.

## Raison

La Période est **déjà** la source analytique **par construction** ; le verrou ne sécurisait qu'un
**couplage superflu**. Test de suppression : retirer le verrou n'enlève **rien** à l'analytique (elle
lit la Période) et la complexité supprimée — une garde sur le cœur comptable — ne réapparaît nulle
part. KISS : on préfère un **budget d'erreur humaine borné** à une garde fragile et coûteuse à
maintenir sur `account.move.line`.

Résout les trois questions ouvertes de
[#35](https://github.com/Energie-De-Nantes/souscriptions_odoo/issues/35) (verrou à la création/émission ;
modélisation du geste commercial ; remise vs régularisation).

## Amendement (#266) — de la dérive tolérée à la gouvernance par provenance

Décision re-instruite dans le cadre du PRD #264 (Brouillon gouverné, grillé le 2026-07-13),
tranche 2. La décision 3 ci-dessus (« dérive tolérée et bornée ») supposait une Facture
statique une fois créée : toute retouche manuelle, comme toute divergence avec la Période,
restait acquise jusqu'à l'émission. Cette hypothèse ne tient plus : la Facture vit désormais en
deux temps (tranche 1, #265 — imputation du chèque énergie déplacée à l'émission ; ce chantier —
re-génération des lignes à l'émission). Sans distinction de provenance, une re-génération
écraserait indistinctement les lignes composées **et** les gestes commerciaux du·de la
facturiste : la dérive resterait tolérée, mais ne serait **plus bornée**.

**Ce qui change.** Un champ de provenance (`souscription_ligne_generee`, `copy=False`) marque
les lignes **générées** — posé par LA composition, pour toutes les sources (Période, Régularisation,
Refacturations rassemblées). L'émission re-génère : supprime les lignes flaguées, recompose
depuis la source, **préserve tout le reste**. Enforcement doux, dans l'esprit de la décision
initiale (**pas** de verrou dur) : readonly en **vue** sur les lignes flaguées (pas de retouche
« acceptée puis écrasée en douce ») + garde `ondelete` étroite (pas de suppression directe d'une
ligne générée). **Toujours aucune surcharge de `write()`** sur `account.move.line` — la raison
d'être de la décision 2 (éviter de combattre les recomputes ORM sur la table la plus chaude
d'Odoo) reste entière ; la voie script/RPC reste ouverte, assumée, la re-génération à l'émission
garantissant la conformité du document final.

**Ce qui ne change pas.** La Période reste la source analytique ; la Facture en reste la
projection (décision 2, inchangée). La confiance au·à la facturiste (décision 4, geste commercial
à son jugement) reste entière — elle est désormais **structurée** : une ligne manuelle ajoutée au
brouillon est identifiable par construction (absence du flag) et survit à toute re-génération,
au lieu de reposer sur le seul fait qu'aucun mécanisme ne la touche. « Dérive manuelle bornée » —
le budget d'erreur humaine de la décision 3 — devient donc une **dérive gouvernée par
provenance** : bornée dans l'espace (une ligne manuelle, jamais une ligne générée) plutôt que
seulement dans le temps (jusqu'à l'émission).
