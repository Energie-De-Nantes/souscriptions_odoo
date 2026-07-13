# Le snapshot figé de la Période fait autorité à la facturation ; pas de repli sur la Souscription live

La composition de la facture d'énergie (quelles lignes, quelles quantités, quelles
notes TURPE) vit désormais sur la *Période* — `souscription.periode._composer_lignes(grille)`
renvoie les lignes, `_creer_facture()` les emballe dans l'`account.move`, et
`souscription.creer_factures()` ne reste qu'orchestrateur (boucle + garde anti-doublon).
Ce déplacement colle le code à `CONTEXT.md` (« la *Période* porte ce qui est **facturé** »)
et à [ADR-0004](0004-lien-periode-facture-source-unique.md) (« une facture facture une
période »).

**Décision.** À la facturation, **toutes** les valeurs contractuelles (type de tarif,
puissance, coeff PRO, tarif solidaire, provisions) proviennent **exclusivement du snapshot
figé** sur la Période à sa création. La composition **ne lit jamais** l'état *live* de la
*Souscription*. On **supprime** les trois replis qui existaient
(`periode.puissance_souscrite_periode or self.puissance_souscrite`,
`periode.type_tarif_periode or <live>`, `coeff_pro_periode` derrière un `hasattr` toujours
vrai) : le snapshot est l'unique source.

Les prix restent l'affaire de la *Grille de prix* passée en paramètre — la Période compose
les quantités et la structure, la Grille fournit les prix
([ADR-0002](0002-deux-sources-de-verite-marge-en-analytique.md), « référencer, pas recopier »).

## Conséquences

- **Comportement constant pour les données réelles.** Le snapshot est peuplé
  inconditionnellement dans `souscription.periode.create()` (et `puissance`/`type_tarif`
  sont requis sur la Souscription) : pour toute Période créée normalement, lire le snapshot
  donne le même résultat que l'ancien `snapshot or live`. La suppression du repli retire du
  **code mort**, pas un cas d'usage.
- **Reproductibilité.** Modifier la Souscription après création d'une Période (changement de
  puissance, de tarif…) ne change plus la facture de cette Période — ce qui est précisément
  l'intention de l'historisation ([ADR-0002](0002-deux-sources-de-verite-marge-en-analytique.md)).
- **Surface de test déplacée à l'interface.** `_composer_lignes(grille)` se teste sur la liste
  de lignes renvoyée — sans créer ni comptabiliser de move. Les ~24 sites de test passent de
  `souscription._creer_facture_periode(periode)` à `periode._creer_facture()`, sans coquille
  de compatibilité.
- **N'efface pas les bricoles de typage.** Le snapshot reste partiellement stringly-typed
  (`"6 kVA"`, libellé `"Base"`), donc `_composer_lignes` hérite encore du parsing
  (`float("6 kVA"…)`, `'Base' in str(...)`). Leur nettoyage est le **snapshot typé** de
  [ADR-0005](0005-granularite-energie-calendrier-comptage.md) / issue #14, hors de ce périmètre.

## Options écartées

- **Garder le repli sur l'état live** (robustesse si un champ historisé manque) : rend la
  facture dépendante de modifications postérieures de la Souscription, ce qui casse la
  reproductibilité ; et le repli était de toute façon inatteignable en pratique.
- **Coquille de compatibilité `souscription._creer_facture_periode`** : maintient une
  interface superficielle (pass-through) — exactement ce que ce refactor supprime.

## Raison

Une facture émise doit être **rejouable à l'identique** depuis ce que la Période a gelé, pas
depuis un état contractuel qui a pu dériver. Faire de la Période l'unique source à la
facturation concentre la logique (locality) et ramène la surface de test à une seule
interface (`_composer_lignes`), au lieu d'un graphe de records + un move comptabilisé.

## Amendement (#267) — le snapshot fait autorité une fois la facture ÉMISE

Décision re-instruite dans le cadre du PRD #264 (Brouillon gouverné, grillé le 2026-07-13),
tranche 3 — voir [ADR-0032](0032-brouillon-gouverne-gel-a-lemission.md) pour la décision
complète. Ce que ce document appelait « la facturation » (le moment où le snapshot fige)
supposait une facture créée = une facture figée : `_creer_facture()` tamponnait la
provision et `souscription.periode.write()` verrouillait dès que `facture_id` existait, y
compris en brouillon ([ADR-0007](0007-snapshot-periode-type-verrou-facturation.md)).

Cette hypothèse ne tient plus. La Facture vit désormais en deux temps (brouillon éditable,
émission qui fige — CONTEXT.md « Facture ») ; le snapshot lui-même reste posé **à la
création** de la Période (inchangé, décision toujours valide ci-dessus), mais ce qui « fait
autorité » — au sens où plus rien ne peut le contredire — ne le devient qu'à l'**émission**.
Pendant la fenêtre brouillon, la Période reste éditable et son brouillon de Facture se
régénère au fil de l'eau (`souscription.periode._est_facturee_emise`, `write()`,
`account.move._recomposer_lignes_generees`). Le principe qui motivait cet ADR — pas de repli
sur l'état *live* de la Souscription, reproductibilité de la facture depuis ce qui a été
gelé — reste entier ; seul le **moment** où ce gel devient irréversible se déplace de « la
Période a une Facture » à « la Facture référençant la Période est postée ».
