"""Amorce l'identité/atterrissage v3 sur les Périodes existantes (#76, ADR 0020).

`souscription.periode.mois` est un nouveau champ calculé/stocké (dérivé de
`date_debut`) : on force son recalcul sur une base existante, comme pour
`facture_id` (migration 19.0.1.1.0).

`ref_situation_contractuelle` n'est snapshotté qu'à la *création* d'une
Période (#76) : sur une base existante, les périodes déjà créées n'ont jamais
eu cette occasion. Best-effort : on recopie la RSC courante de la Souscription
quand elle en porte une — mieux qu'un champ vide, sans prétendre reconstituer
un historique qui n'existait pas avant cette version. Les périodes déjà
**facturées** sont figées (#14) : on les laisse telles quelles plutôt que de
contourner le verrou pour une donnée qui n'existait pas au moment de la
facturation.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    Periode = env['souscription.periode']
    periodes = Periode.search([])
    if periodes:
        periodes.invalidate_recordset(['mois'])
        periodes._compute_mois()
        periodes.flush_recordset(['mois'])

        a_completer = periodes.filtered(lambda p: not p.ref_situation_contractuelle and not p.facture_id)
        for periode in a_completer:
            rsc = periode.souscription_id.ref_situation_contractuelle
            if rsc:
                periode.ref_situation_contractuelle = rsc
