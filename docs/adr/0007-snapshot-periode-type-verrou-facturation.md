# Snapshot de Période typé et verrou à l'émission de la facture

Le snapshot contractuel figé sur la *Période* à sa création
([ADR-0006](0006-snapshot-periode-fait-autorite-facturation.md)) était *stringly-typed* :
`puissance_souscrite_periode` était un `Char` `"6 kVA"` re-parsé par regex à la facturation,
et `type_tarif_periode` un `Char` portant le **libellé traduit** `"Base"`, comparé par
sniffing (`'Base' in str(...)`). Ces deux bricoles sont **fragiles** (dépendance à la langue,
au formatage) et étaient explicitement renvoyées à l'issue #14. Par ailleurs, rien
n'empêchait de **réécrire** une *Période* dont la *Facture* était déjà **émise** — y compris
via RPC — ce qui désaccordait silencieusement une facture opposable de son snapshot.

## Décision

1. **Snapshot typé.** `type_tarif_periode` devient un `Selection` (`base`/`hphc`, mêmes clés
   que `souscription.type_tarif`) et `puissance_souscrite_periode` un `Float` (kVA). La
   composition (`_composer_lignes`) les lit **directement**, sans aucun parsing :
   `puissance_kva = self.puissance_souscrite_periode`, `is_base = type_tarif_periode == 'base'`.
   Le `Float` (plutôt que `Selection` de paliers) garde la porte ouverte à une tarification
   **affine** (part fixe + €/kVA) au grain 1 kVA d'Enedis ; la *Grille* reste indexée par
   palier pour l'instant (tarification affine = travail ultérieur).

2. **Verrou à l'émission.** `souscription.periode.write()` **rejette** (`UserError`) toute
   modification d'un champ **facturable** dès que la *Facture* liée est **émise**
   (`facture_id.state == 'posted'`). Les corrections se font *avant* l'émission, sur une
   *Facture* en **brouillon** — cohérent avec le rôle de la *Période* (« brouillon de travail
   facturable », `CONTEXT.md`) et avec la distinction *facturée* / *émise*
   ([ADR-0004](0004-lien-periode-facture-source-unique.md)).

3. **Suppression des champs de compatibilité** dépréciés (`energie_kwh`, `provision_kwh`,
   `_fix_provision`) et de leurs computes, ainsi que du champ *live* `type_tarif`
   (related) de la Période : les vues s'appuient désormais sur le type **historisé**.

## Conséquences

- **Plus de parsing à la facturation** : la justesse ne dépend plus de la langue ni du
  formatage du snapshot.
- **Reproductibilité renforcée** : une facture émise ne peut plus dériver de son snapshot ;
  la régularisation (période dédiée) reste le canal pour corriger après émission.
- **Périmètre du verrou.** Seuls les champs facturables sont protégés (un `frozenset`
  `_LOCKED_FIELDS` : dates, énergies par cadran, provisions, TURPE, snapshot contractuel).
  Les champs techniques/calculés (`facture_id`, `facture_state`, `mois_annee`, `jours`)
  restent recalculables : l'ORM les écrit par `_write`, pas par le `write()` public surchargé,
  donc le verrou ne gêne pas les recomputes.
- **Migration.** Refonte *greenfield* (Odoo 19, données démo régénérées,
  [ADR-0003](0003-strategie-migration-odoo19-odoo-sh.md)) : pas de script de bascule des
  anciennes valeurs `Char` (`"6 kVA"`, `"Base"`) — aucune donnée legacy à convertir.

## Options écartées

- **`puissance_souscrite_periode` en `Selection` de paliers** : plus contraint, mais ferme la
  porte à la tarification affine au grain 1 kVA souhaitée côté fournisseur.
- **Verrou dès qu'une facture existe (brouillon compris)** : contredit le workflow
  « brouillon corrigé avant émission » ; le·la facturiste doit pouvoir ajuster tant que la
  facture n'est pas postée.
- **Bloquer *tous* les champs en écriture quand verrouillé** : casserait les recomputes ORM
  légitimes ; l'allowlist par `frozenset` cible exactement l'intention.

## Raison

Achever la « refonte propre » du modèle Période (#14) : un snapshot **typé** supprime la
dette de parsing, et le **verrou à l'émission** fait du couple Période/Facture un objet
**rejouable et opposable**, sans surface d'altération a posteriori.
