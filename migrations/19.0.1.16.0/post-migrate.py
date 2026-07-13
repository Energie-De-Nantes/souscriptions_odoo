"""Backfill provenance : flague « générées » (`souscription_ligne_generee`) les
lignes des factures d'énergie EN BROUILLON existantes (#266, ADR 0014 amendé,
tranche 2 du PRD #264).

Avant cette version, aucune ligne ne portait le flag de provenance — la
distinction générée/manuelle n'existait pas. Au déploiement, toute ligne
« produit »/section/note d'un brouillon de facture d'énergie (source Période
OU Régularisation, ADR 0030 décision 5) est présumée générée : c'est la
population réelle à cette date, aucun geste commercial « ligne manuelle » au
sens de ce chantier n'existant avant cette tranche. Une facture déjà POSTÉE
n'est pas concernée (l'enforcement doux — readonly vue + garde `ondelete` —
ne s'applique qu'au brouillon ; une facture postée ne sera jamais régénérée).

Scope `display_type IN ('product', 'line_section', 'line_note')` : ce sont
EXACTEMENT les lignes que composent `souscription.periode._composer_lignes`,
`souscription.refacturation._composer_ligne` et
`souscription.regularisation._composer_lignes` — jamais les lignes de taxe/
acompte/échéance (`tax`, `payment_term`, `rounding`, `epd`…) qu'Odoo gère et
recompose lui-même. Flaguer ces dernières bloquerait le recompute natif
d'Odoo derrière la garde `ondelete` de `account.move.line` — à éviter
absolument.

SQL direct (comme 19.0.1.14.0/post-migrate.py) : backfill de masse, plus
sûr/rapide qu'un `write()` par ligne (le champ n'est pas verrouillé, mais rien
n'oblige à passer par l'ORM pour un simple drapeau). Idempotent : ne touche
que les lignes pas déjà flaguées.
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE account_move_line l
        SET souscription_ligne_generee = TRUE
        FROM account_move m
        WHERE l.move_id = m.id
          AND m.state = 'draft'
          AND (m.periode_id IS NOT NULL OR m.regularisation_id IS NOT NULL)
          AND l.display_type IN ('product', 'line_section', 'line_note')
          AND l.souscription_ligne_generee IS NOT TRUE
        """
    )
