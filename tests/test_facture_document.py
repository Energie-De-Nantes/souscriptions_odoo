"""Rendu de la Facture d'énergie — PDF et aperçu HTML (#221).

La Facture n'est pas une projection contractuelle (contrairement aux
Conditions particulières/Attestation, cf. test_documents_contractuels.py) :
elle porte sa propre petite suite HttpCase, récupérée de l'ex `test_ui.py`
(`TestSouscriptionsReports`).
"""

from odoo.tests.common import HttpCase, tagged

from .common import SouscriptionsTestMixin

PDF_URL = '/report/pdf/souscriptions_odoo.report_facture_energie/%s'
HTML_URL = '/report/html/souscriptions_odoo.report_facture_energie/%s'


@tagged('souscriptions', 'souscriptions_facture_document', 'post_install', '-at_install')
class TestFactureEnergieDocument(SouscriptionsTestMixin, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        periode = cls.env['souscription.periode'].create(
            {
                'souscription_id': cls.souscription_base.id,
                'date_debut': '2024-01-01',
                'date_fin': '2024-01-31',
                'type_periode': 'mensuelle',
                'jours': 31,
                'energie_hph_kwh': 140.0,
                'energie_hpb_kwh': 56.0,
                'energie_hch_kwh': 56.0,
                'energie_hcb_kwh': 28.0,
                'turpe_fixe': 8.5,
                'turpe_variable': 4.2,
            }
        )
        cls.facture_test = periode._creer_facture()

    def test_facture_energie_pdf(self):
        """Le PDF de la facture d'énergie se génère sans erreur."""
        self.authenticate('admin', 'admin')
        response = self.url_open(PDF_URL % self.facture_test.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'application/pdf')
        self.assertGreater(len(response.content), 1000)  # Un PDF minimal fait plus de 1KB

    def test_facture_energie_html_preview(self):
        """L'aperçu HTML porte les informations clés de la Souscription/Période."""
        self.authenticate('admin', 'admin')
        response = self.url_open(HTML_URL % self.facture_test.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn('PDL_TEST_STANDARD', response.text)
        self.assertIn('dont turpe', response.text.lower())
