# Identité de la *Souscription* : la RSC comme clé, l'`id_Affaire` comme amorce de réconciliation

La *Souscription* était entièrement clée sur le **PDL**, qui n'est pas un identifiant de
contrat : un même PDL est attribué à plusieurs *souscripteur·rice·s* successif·ves (issue #5).
electricore travaille en **`ref_situation_contractuelle`** (RSC), unique par couple
(PDL, usager·ère), et c'est sur la RSC que sont clées les *méta-périodes* qu'Odoo tire
([ADR-0001](0001-odoo-systeme-ecriture-electricore-api-read-only.md)). Mais la RSC **n'est pas
affichée dans SGE** : un humain ne peut pas la saisir à la création. L'**`id_Affaire`** Enedis —
la référence d'affaire renvoyée dès la demande de raccordement — est, elle, **connue tôt** et
**non ambiguë par affaire**.

## Décision

1. **Deux identifiants stockés sur la *Souscription*.** `ref_situation_contractuelle` est la
   **clé d'articulation** (ce sur quoi le *pull* est clé) ; `id_affaire` est l'**amorce de
   réconciliation** (audit + ré-résolution). Le **PDL** redevient un simple attribut
   d'affichage/recherche.

2. **`id_Affaire` capturé au raccordement.** Nouveau champ sur `raccordement.demande`, recopié
   sur la *Souscription* qu'il engendre. C'est le seul identifiant à la fois disponible **tôt**
   (avant tout C15) et **non ambigu**.

3. **Réconciliation à la bascule « raccordement effectué ».** À cette transition — qui
   **conditionne aussi la facturabilité** — Odoo appelle l'endpoint de résolution d'electricore
   (`id_Affaire → RSC`, via le flux **X12** recoupé avec l'`id_Affaire` que porte aussi le C15)
   et **inscrit la RSC** sur la *Souscription*. electricore *calcule-et-renvoie* la RSC ;
   **Odoo écrit son propre champ** — le read-only-vers-Odoo est préservé
   ([ADR-0001](0001-odoo-systeme-ecriture-electricore-api-read-only.md)).

4. **Aucun repli flou sur le flux vif.** La facturation ne démarrant qu'après « raccordement
   effectué » (⇒ MES ⇒ C15/X12 existent ⇒ RSC résoluble), la RSC est **toujours présente au
   moment de facturer**. Le couple **PDL + date** ne survit **que** comme outil de **migration
   unique** du legacy, jamais dans le flux de facturation courant.

## Conséquences

- Nouveaux champs `ref_situation_contractuelle` et `id_affaire` (Souscription) + `id_affaire`
  (raccordement) ; refonte *greenfield*
  ([ADR-0003](0003-strategie-migration-odoo19-odoo-sh.md)), pas de bascule de données legacy.
- electricore expose un endpoint de **résolution RSC** (lecture) et **cesse de lire `sale.order`**
  pour faire ce rapprochement (il le faisait côté legacy ; AUDIT §3.2/§3.3).
- Réponse explicite à l'**issue #5** : la RSC est **récupérée** par l'`id_Affaire`, pas saisie à
  la main.
- La *Souscription* devient **facturable** uniquement raccordement effectué (donc RSC présente) —
  pré-condition reprise par
  [ADR-0011](0011-contrat-pull-facturation-electricore-cle-rsc-mois.md).

## Options écartées

- **Garder le PDL comme clé** : ambigu sur les *souscripteur·rice·s* successif·ves (le problème
  même de #5).
- **Saisie manuelle de la RSC** : impossible, la RSC n'est pas affichée dans SGE.
- **Clé unique sur `id_Affaire`, RSC laissée côté electricore** : contredit l'intention « la
  *Souscription* porte la RSC comme clé d'articulation » (`CONTEXT.md`) et couplerait **chaque**
  *pull* à une traduction vive `id_Affaire → RSC`.
- **Repli PDL + date sur le flux vif** : risque de router une *méta-période* vers le **mauvais·e
  souscripteur·rice** (mésfacturation silencieuse) — réservé à la migration.

## Raison

L'`id_Affaire` est le **seul** identifiant à la fois connu tôt (dès la demande) et non ambigu ;
il sert d'amorce robuste pour acquérir **une fois** la RSC, qui reste la **clé durable** de tout
l'échange. Correction avant automatisation : un contrat non réconcilié n'est **pas** facturé
automatiquement plutôt que facturé sur une correspondance douteuse.
