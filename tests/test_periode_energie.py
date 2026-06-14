"""
Tests énergie de la période (issue #26 / ADR 0005).

`config_cadrans` (calendrier de comptage) pilote le niveau de saisie ; l'énergie
est une cascade dérivée-mais-surchargeable HPH/HPB/HCH/HCB → HP/HC → BASE.
"""

from datetime import date

from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_periode_energie', 'post_install', '-at_install')
class TestPeriodeEnergie(SouscriptionsTestCase):
    def _periode(self, souscription, **vals):
        base = {
            'souscription_id': souscription.id,
            'date_debut': date(2024, 1, 1),
            'date_fin': date(2024, 1, 31),
            'type_periode': 'mensuelle',
        }
        base.update(vals)
        return self.env['souscription.periode'].create(base)

    def test_config_cadrans_historise_a_la_creation(self):
        """La période fige le calendrier de comptage de la souscription à sa création."""
        self.souscription_base.config_cadrans = '4_cadrans'
        periode = self._periode(self.souscription_base)
        self.assertEqual(periode.config_cadrans, '4_cadrans')

    def test_cascade_4_cadrans(self):
        """4_cadrans : la saisie des 4 cadrans dérive HP/HC/BASE."""
        self.souscription_base.config_cadrans = '4_cadrans'
        p = self._periode(
            self.souscription_base, energie_hph_kwh=130, energie_hpb_kwh=85, energie_hch_kwh=60, energie_hcb_kwh=35
        )
        self.assertEqual(p.energie_hp_kwh, 215)
        self.assertEqual(p.energie_hc_kwh, 95)
        self.assertEqual(p.energie_base_kwh, 310)

    def test_cascade_hp_hc(self):
        """hp_hc : la saisie directe de HP/HC dérive BASE, sans cadrans."""
        self.souscription_base.config_cadrans = 'hp_hc'
        p = self._periode(self.souscription_base, energie_hp_kwh=215, energie_hc_kwh=95)
        self.assertEqual(p.energie_hp_kwh, 215)
        self.assertEqual(p.energie_hc_kwh, 95)
        self.assertEqual(p.energie_base_kwh, 310)
        self.assertEqual(p.energie_hph_kwh, 0)

    def test_cascade_base(self):
        """base : la saisie directe de BASE, sans HP/HC ni cadrans."""
        self.souscription_base.config_cadrans = 'base'
        p = self._periode(self.souscription_base, energie_base_kwh=310)
        self.assertEqual(p.energie_base_kwh, 310)
        self.assertEqual(p.energie_hp_kwh, 0)
        self.assertEqual(p.energie_hc_kwh, 0)

    def test_saisie_non_ecrasee_par_recompute(self):
        """Une valeur saisie n'est pas écrasée par un recalcul déclenché ailleurs."""
        self.souscription_base.config_cadrans = 'hp_hc'
        p = self._periode(self.souscription_base, energie_hp_kwh=215, energie_hc_kwh=95)
        p.write({'turpe_fixe': 9.0})
        self.assertEqual(p.energie_hp_kwh, 215)
        self.assertEqual(p.energie_base_kwh, 310)

    def test_ecart_base(self):
        """Écart BASE = réel − provision."""
        self.souscription_base.config_cadrans = 'base'
        p = self._periode(self.souscription_base, energie_base_kwh=310, provision_base_kwh=320)
        self.assertEqual(p.ecart_base_kwh, -10)

    def test_ecart_hp_hc(self):
        """Écart HP/HC = réel − provision par cadran facturé."""
        self.souscription_base.config_cadrans = 'hp_hc'
        p = self._periode(
            self.souscription_base, energie_hp_kwh=215, energie_hc_kwh=95, provision_hp_kwh=224, provision_hc_kwh=96
        )
        self.assertEqual(p.ecart_hp_kwh, -9)
        self.assertEqual(p.ecart_hc_kwh, -1)
