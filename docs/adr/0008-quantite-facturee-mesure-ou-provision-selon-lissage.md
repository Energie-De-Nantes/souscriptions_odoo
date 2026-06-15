# Quantité d'énergie facturée : le mesuré si non lissé, la provision si lissé

La composition de facture ([ADR-0006](0006-snapshot-periode-fait-autorite-facturation.md))
portait **toujours** `provision_*_kwh` comme quantité d'énergie, quel que soit le contrat.
Conséquence : pour un contrat **non lissé**, il fallait recopier le mesuré dans la provision
(les jeux de test le faisaient à la main), et la vue Période juxtaposait sans le dire un
groupe *mesuré* (`energie_*`) et un groupe *provision* (`provision_*`) tous deux étiquetés
« Facturé » — illisible (issue #14, objectif « clarifier provision vs consommation réelle »).

## Décision

La quantité facturée par cadran dépend du **lissage** (snapshot figé `lisse_periode`) :

- **Non lissé** → on facture le **mesuré / estimé** (`energie_*_kwh`) directement.
- **Lissé** → on facture la **provision** contractuelle (`provision_*_kwh`) ; l'écart avec le
  mesuré (`ecart_*_kwh = mesuré − provision`) est suivi et soldé plus tard en **régularisation**.

Le choix est centralisé dans `souscription.periode._quantite_facturee(cadran)`, lu par
`_composer_lignes`. Les prix restent l'affaire de la *Grille*
([ADR-0002](0002-deux-sources-de-verite-marge-en-analytique.md)).

Côté vue, les deux concepts sont désormais nommés distinctement : groupe **« Mesuré / estimé »**
(`energie_*`) vs **« Provision & écart »** (`provision_*` + `ecart_*`, visible si lissé).

## Conséquences

- **Le non lissé facture le réel sans recopie.** Plus besoin d'alimenter `provision_*` pour un
  contrat au réel : `energie_*` (mesure Enedis ou estimation du·de la facturiste) suffit.
- **`provision_*` redevient strictement « la provision »** (cas lissé), conforme au vocabulaire
  métier (electricore : *provision d'énergie*, *contrat lissé*, *régularisation*).
- **Tests.** Les scénarios non lissés portent l'énergie attendue dans `energie_*` (et non plus
  `provision_*`). Le cas lissé (provision facturée) reste couvert tel quel.
- **Cohérence du verrou** ([ADR-0007](0007-snapshot-periode-type-verrou-facturation.md)) :
  `energie_*` et `provision_*` sont tous deux des champs facturables verrouillés à l'émission.

## Options écartées

- **Toujours facturer `provision_*`** (état antérieur) : oblige à dupliquer le mesuré dans la
  provision pour le non lissé et brouille la sémantique provision/réel.
- **Toujours facturer `energie_*`** : casse le lissage (on doit facturer la provision, pas le
  réel, tant que la régularisation n'a pas eu lieu).
- **Un seul champ « quantité facturée »** fusionnant les deux : perd la distinction
  mesuré/provision nécessaire au calcul de l'écart et à la régularisation.

## Raison

Coller la facturation au sens métier : au réel on facture le réel, en lissé on facture la
provision et on régularise. C'est la résolution de l'objectif #14 « clarifier provision vs
consommation réelle », et la suite logique du renommage *Mesuré / estimé* vs *Provision* sur la
vue Période.
