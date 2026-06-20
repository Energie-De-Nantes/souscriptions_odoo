"""
Rendu du rapport de contrat de souscription (#50).

Garde-fou de comportement pour la migration ``t-esc`` -> ``t-out`` : le rapport
de contrat formate le prix unitaire des lignes de grille avec ``'%.4f' %`` (cf.
reports/souscription_contrat_report.xml). On vérifie que ce formatage à quatre
décimales survit au rendu, indépendamment de la directive QWeb utilisée.
"""

from odoo.addons.souscriptions_odoo.tests.common import SouscriptionsTestMixin
from odoo.tests.common import HttpCase, tagged


@tagged('post_install', '-at_install', 'souscriptions_reports')
class ContratReportTestCase(SouscriptionsTestMixin, HttpCase):
    """Le rapport de contrat rend la tarification avec son formatage intact."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()

    def _report_url(self, souscription=None):
        souscription = souscription or self.souscription_base
        return f'/report/html/souscriptions_odoo.souscription_contrat_document/{souscription.id}'

    def test_contrat_rend_prix_unitaire_a_quatre_decimales(self):
        """Le prix énergie (0,15) apparaît formaté à 4 décimales (« 0.1500 »).

        La grille active de test (cf. common.py) porte un prix énergie Base de
        0.15 €. Le rapport l'affiche via ``'%.4f' % ligne.prix_unitaire`` : on
        attend donc « 0.1500 » dans la page. Si le formatage saute, c'est « 0.15 »
        qui sortirait et l'assertion casse.
        """
        self.authenticate('admin', 'admin')
        response = self.url_open(self._report_url())

        self.assertEqual(response.status_code, 200)
        self.assertIn('CONTRAT DE FOURNITURE', response.text)
        self.assertIn('0.1500', response.text)
