# Journal des actes unifié : les actes d'adhésion rejoignent le journal de consentement

La *Souscription* trace **tous les actes** du·de la *souscripteur·rice* — consentements RGPD
**et** actes d'adhésion contractuels (acceptation CGV, renonciation au délai de rétractation) —
dans le **même journal append-only** (`souscription.consentement`, ADR 0017), rebaptisé
***Journal des actes*** dans le vocabulaire (le nom technique du modèle ne change pas : renommer
la table serait du churn de migration sans gain). Les champs plats `date_validation` et
`renonce_retractation` de la souscription sont **supprimés** ; les *conditions particulières*
lisent le journal (dernière ligne par finalité). Les finalités contractuelles sont
**irrévocables** : le journal **refuse** un retrait sur `acceptation_cgv` /
`renonciation_retractation` — on ne « retire » pas une signature.

Motif : un seul registre de preuves (horodatage + **version du texte montré** + source), la même
garantie d'intégrité texte↔preuve que l'ADR 0017, au lieu de deux mécanismes parallèles — journal
riche pour le RGPD, champs plats **muets** (ni texte, ni source) pour le contractuel. La preuve
d'époque **existe** : le kanban prod (`x_souscription_differe`) enregistre le texte validé au
formulaire (`x_cgv`, `x_responsabilite`) et l'horodatage de soumission (`x_date_soumission_form`).
La **reprise est portée par le pipeline** `souscriptions_migration`, qui crée les lignes de
journal avec ces textes réels.

## Options considérées

- **Statu quo (champs plats conservés)** — deux natures de preuve ; la CP imprime depuis des
  champs sans texte ni source ; la section « Adhésion » du formulaire fait doublon visuel avec le
  journal affiché dessous. Rejeté.
- **Deux journaux séparés** (consentements / actes d'adhésion) — duplique la mécanique
  append-only pour distinguer ce que la colonne `finalite` distingue déjà. Rejeté.
- **Sémantique donné/retiré étendue telle quelle aux actes contractuels** — un « retrait »
  d'acceptation CGV est juridiquement absurde. Rejeté au profit du garde d'irrévocabilité : même
  table, natures distinguées par finalité, retrait refusé sur les irrévocables.
- **Pre-migrate défensif dans l'addon** (conversion champs plats → lignes sentinelles à
  l'upgrade) — protégerait une base qui porte ces données **et** n'est pas reconstructible par le
  pipeline ; cette base n'existe pas (prodlocal est un produit du pipeline, re-runnable). Rejeté
  (YAGNI) ; en contrepartie l'ordre de déploiement est contraint (voir Conséquences).

## Conséquences

- `souscription.consentement` gagne deux finalités (`acceptation_cgv`,
  `renonciation_retractation`) et un garde : le **retrait** (ligne `etat = retire`) est refusé
  sur ces finalités — write/unlink restent interdits (append-only, ADR 0017).
- Le *raccordement* **journalise** ces actes à la création de la souscription (comme les deux
  finalités RGPD) au lieu de recopier des champs ; ses champs d'intake restent sur la demande
  (transitoire).
- La CP lit la **dernière ligne** par finalité : « Adhésion validée le » depuis
  `acceptation_cgv`, paragraphe de renonciation si une ligne `renonciation_retractation` existe ;
  **absence de ligne = pas de mention** (pas d'acte = pas de preuve).
- Reprise (pipeline) : `x_cgv` → ligne `acceptation_cgv` ; `x_responsabilite` → ligne
  `renonciation_retractation` quand une variante « rapide » (exécution avant la fin du délai) est
  présente, **y compris en double coche** « rapide, 15j » ; horodatage = `x_date_soumission_form`,
  `version_texte` = le texte/slug d'époque tel quel (les variantes « 14 jours »/« 15 jours »
  d'époque sont conservées telles quelles — c'est précisément l'intérêt de journaliser le texte),
  `source` = reprise kanban.
- **Ordre de déploiement** : re-runner le pipeline **immédiatement après** l'upgrade — le `-u`
  droppe les colonnes plates, les mentions CP des souscriptions existantes sont vides entre les
  deux.
