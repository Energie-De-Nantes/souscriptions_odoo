"""Recalcule `souscription.periode.facture_id` (issue #23 / ADR 0004).

`facture_id` devient un champ calculé/stocké dérivé de `account.move.periode_id`.
Sur une base existante, les lignes ont l'ancienne valeur écrite à la main (ou
vide pour les périodes facturées uniquement via le lien côté facture) : on force
le recalcul à partir de la source de vérité unique.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    periodes = env['souscription.periode'].search([])
    if not periodes:
        return
    periodes.invalidate_recordset(['facture_id'])
    periodes._compute_facture_id()
    periodes.flush_recordset(['facture_id'])
