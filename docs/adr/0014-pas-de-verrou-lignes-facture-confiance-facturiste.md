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
