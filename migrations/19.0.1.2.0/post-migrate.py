"""Amorce `config_cadrans` (calendrier de comptage) — issue #26 / ADR 0005.

Nouveau pilote de la granularité énergie. Sur une base existante :
- souscriptions : amorçage depuis le type de tarif (base → `base`, hphc → `4_cadrans`) ;
- périodes : déduction du calendrier depuis les données déjà saisies, pour que la
  cascade énergie reste cohérente (les valeurs existantes ne sont pas écrasées : les
  computes config-aware conservent un niveau saisi directement).
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    Sous = env['souscription.souscription']
    for sous in Sous.search([('config_cadrans', '=', False)]):
        sous.config_cadrans = '4_cadrans' if sous.type_tarif == 'hphc' else 'base'

    Periode = env['souscription.periode']
    for p in Periode.search([('config_cadrans', '=', False)]):
        if any((p.energie_hph_kwh, p.energie_hpb_kwh, p.energie_hch_kwh, p.energie_hcb_kwh)):
            p.config_cadrans = '4_cadrans'
        elif p.energie_hp_kwh or p.energie_hc_kwh:
            p.config_cadrans = 'hp_hc'
        elif p.energie_base_kwh:
            p.config_cadrans = 'base'
        else:
            p.config_cadrans = p.souscription_id.config_cadrans or (
                '4_cadrans' if p.souscription_id.type_tarif == 'hphc' else 'base'
            )
