"""
Tests du formulaire période (issue #27 / ADR 0005).

La section énergie est pilotée par le calendrier de comptage (config_cadrans) :
le niveau de saisie suit le compteur. Champs compat retirés des vues.
"""

from odoo.tests.common import Form, tagged
from datetime import date

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_periode_form', 'post_install', '-at_install')
class TestPeriodeForm(SouscriptionsTestCase):

    def _periode(self, souscription, config):
        souscription.config_cadrans = config
        return self.env['souscription.periode'].create({
            'souscription_id': souscription.id,
            'date_debut': date(2024, 1, 1),
            'date_fin': date(2024, 1, 31),
        })

    def test_form_periode_se_charge(self):
        """Le formulaire période dédié se charge sans erreur."""
        periode = self._periode(self.souscription_base, '4_cadrans')
        with Form(periode):
            pass

    def test_config_base_saisie_base_cadrans_masques(self):
        """config base : BASE saisissable, cadrans réseau masqués."""
        periode = self._periode(self.souscription_base, 'base')
        with Form(periode) as f:
            f.energie_base_kwh = 250.0
            with self.assertRaises(Exception):
                f.energie_hph_kwh = 100.0

    def test_config_hp_hc_saisie_hp_hc(self):
        """config hp_hc : HP/HC saisissables, cadrans masqués."""
        periode = self._periode(self.souscription_hphc, 'hp_hc')
        with Form(periode) as f:
            f.energie_hp_kwh = 200.0
            f.energie_hc_kwh = 100.0
            with self.assertRaises(Exception):
                f.energie_hph_kwh = 50.0

    def test_config_4_cadrans_saisie_cadrans(self):
        """config 4_cadrans : les 4 cadrans réseau sont saisissables."""
        periode = self._periode(self.souscription_hphc, '4_cadrans')
        with Form(periode) as f:
            f.energie_hph_kwh = 130.0
            f.energie_hpb_kwh = 85.0
            f.energie_hch_kwh = 60.0
            f.energie_hcb_kwh = 35.0

    def test_champs_compat_absents_du_formulaire(self):
        """Les champs dépréciés ne figurent pas dans le formulaire."""
        view = self.env['souscription.periode'].get_view(view_type='form')
        self.assertNotIn('energie_kwh', view['arch'])
        self.assertNotIn('provision_kwh', view['arch'])

    def test_config_cadrans_editable_sur_souscription(self):
        """Le calendrier de comptage est réglable depuis la souscription."""
        with Form(self.souscription_base) as f:
            f.config_cadrans = 'hp_hc'
