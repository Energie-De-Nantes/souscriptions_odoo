# Prestation : état dérivé et mise en attente manuelle (opt-out de la facturation automatique)

Le·la *facturiste* a besoin d'un écran pour **vérifier les prestations avant facturation** (terme
**Facturiste** dans `CONTEXT.md`) : repérer les montants élevés, et **écarter** les prestations
douteuses de la facturation automatique le temps de lever le doute. On ajoute à
`souscription.presta` (voir [ADR-0009](0009-prestation-refacturer-modele-independant-rassemble-sur-facture.md))
un **état** affichable/groupables et une **mise en attente** manuelle, avec une sémantique
**opt-out, sans garde-fou bloquant**.

**Décision.**

1. **`en_attente` : booléen manuel, posé par le·la facturiste.** Seule information *nouvelle* (non
   dérivable) du modèle : « j'ai un doute, ne pas facturer pour l'instant ». C'est l'unique champ
   ajouté que l'humain renseigne.

2. **`etat` : Selection *stockée mais calculée*, dérivée — pas un doublon.** Valeurs ordonnées
   `a_refacturer → en_attente → facturee → emise` (l'ordre pilote le tri des groupes). Calcul
   `@api.depends('facture_id', 'facture_id.state', 'en_attente')` : `facture_id` **émise** →
   `emise` ; `facture_id` posé (brouillon) → `facturee` ; sinon `en_attente` coché → `en_attente` ;
   sinon `a_refacturer`. **Ne contredit pas** [ADR-0009 §4](0009-prestation-refacturer-modele-independant-rassemble-sur-facture.md) :
   `facture_id` **reste** l'unique source de vérité du « facturé » ; `etat` ne fait que la *projeter*
   pour le groupage et les stats (donc `facture_id` prime, l'`en_attente` d'une presta facturée est
   ignoré et son toggle verrouillé). Stocké uniquement pour pouvoir grouper/filtrer/agréger côté SQL.

3. **`a_refacturer` est l'état par défaut ; la vérification est *opt-out*, pas *opt-in*.** Toute
   prestation est facturable tant qu'on ne l'a pas mise en attente. `souscription.creer_factures()`
   balaie les prestations `facture_id IS NULL` **et** `not en_attente` — la méthode
   `_facturer_prestations_en_attente` est renommée `_facturer_prestations_a_refacturer` (sa
   sémantique : « rassembler ce qui est *à refacturer* », pas « en attente » — cf. la résolution de
   collision de vocabulaire ci-dessous).

4. **Aucun garde-fou bloquant.** Rien n'oblige à consulter l'écran avant `creer_factures` : une
   prestation chère non vérifiée **se facturera**. C'est assumé — la responsabilité de vérifier
   incombe au·à la *facturiste* (cohérent avec le principe « le processus principal d'abord, l'humain
   tranche les cas limites dans l'instant »). L'atténuation est ergonomique (écran trié par prix
   décroissant), pas systémique.

## Résolution de collision de vocabulaire

Avant cet ADR, le code employait « en attente » pour désigner la file `facture_id IS NULL`
(`_facturer_prestations_en_attente`), alors que `CONTEXT.md` la nomme **à refacturer**. On tranche :
**à refacturer** = la file par défaut ; **en attente** = la mise en attente manuelle sur doute. Le
glossaire (`CONTEXT.md`, terme *Prestation*) et le nom de méthode sont alignés sur cette distinction.

## Options écartées

- **Opt-in / file d'approbation** (rien ne se facture sans validation explicite, presta par presta
  ou par lot) : plus sûr, mais alourdit le processus mensuel et déplace le risque vers l'oubli de
  validation. Écarté au profit de l'opt-out (KISS) — la majorité des prestations sont du
  pass-through légitime ([ADR-0009 §6](0009-prestation-refacturer-modele-independant-rassemble-sur-facture.md)).
- **`etat` comme champ Selection éditable** (au lieu de calculé) : permettrait un drag-and-drop
  kanban entre colonnes, mais désynchronise l'état du `facture_id` — exactement le doublon que
  [ADR-0009 §4](0009-prestation-refacturer-modele-independant-rassemble-sur-facture.md) refuse.
  L'`etat` reste dérivé ; seul `en_attente` est éditable.
- **Garde-fou bloquant** (interdire `creer_factures` tant que des prestations chères ne sont pas
  visées) : surcoût et faux sentiment de sécurité ; non aligné avec le rôle *facturiste*.
