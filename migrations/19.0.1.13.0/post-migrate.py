"""Recalcul du champ stocké `iban_valide` des demandes de raccordement (#216).

La validation passe de l'algo maison (≥ 15 caractères + modulo 97) à
`base_iban.validate_iban` (longueur exacte par pays, gabarit ISO 13616).
Odoo ne recompute pas un champ stocké quand seul le corps du compute change :
sans ce script, les lignes existantes garderaient le verdict laxiste jusqu'à
la prochaine écriture de `bank_iban`. Durcissement assumé (#216) : des cartes
en attente peuvent perdre leur badge — c'est la réparation de la divergence
garde/création-banque. Idempotent, no-op sur install neuve.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    demandes = env['raccordement.demande'].search([])
    demandes._compute_iban_valide()
    demandes.flush_recordset(['iban_valide'])
