"""Facture de régularisation — projection des lignes, avoir, chèque énergie,
justificatif (tranche 5 du PRD #231, #237, ADR 0030 décision 3).

La sélection des candidats et la construction des lignes (`_recalculer`) sont
déjà couvertes par test_regularisation.py (tranche 4, #236) : ici, les lignes
de régul sont construites **directement** (grille × cadran, écart, prix,
détail par mois) pour isoler la PROJECTION facture — même séparation de
préoccupations que candidats vs composition côté Période.
"""

from datetime import date

from odoo.exceptions import UserError
from odoo.tests.common import HttpCase, tagged

from .common import SouscriptionsTestCase, SouscriptionsTestMixin

PDF_URL = '/report/pdf/souscriptions_odoo.report_facture_energie/%s'
HTML_URL = '/report/html/souscriptions_odoo.report_facture_energie/%s'


@tagged('souscriptions', 'souscriptions_regularisation', 'post_install', '-at_install')
class TestRegularisationFactureProjection(SouscriptionsTestCase):
    """AC #237 : signe -> facture/avoir, une ligne par grille × cadran, notes
    par mois, produit résolu par le catalogue, verrou."""

    def _regularisation(self, souscription, lignes_vals, date_debut=date(2024, 1, 1), date_fin=date(2024, 2, 1)):
        regularisation = self.env['souscription.regularisation'].create(
            {'souscription_id': souscription.id, 'date_debut': date_debut, 'date_fin': date_fin}
        )
        for vals in lignes_vals:
            defaults = {
                'regularisation_id': regularisation.id,
                'grille_id': self.grille_prix.id,
                'date_debut': date_debut,
                'date_fin': date_fin,
                'tarif_solidaire': False,
            }
            defaults.update(vals)
            self.env['souscription.regularisation.ligne'].create(defaults)
        return regularisation

    def test_ecart_positif_cree_une_facture_complementaire(self):
        """Σ écarts positif -> account.move out_invoice, jamais de total négatif."""
        regularisation = self._regularisation(
            self.souscription_base,
            [{'cadran': 'base', 'ecart_kwh': 50.0, 'prix_kwh': 0.15, 'detail': 'Janvier 2024 : 50.00 kWh'}],
        )

        facture = regularisation._creer_facture()

        self.assertEqual(facture.move_type, 'out_invoice')
        self.assertAlmostEqual(facture.amount_untaxed, 7.5, places=2)
        self.assertGreater(facture.amount_total, 0.0)
        self.assertEqual(regularisation.facture_id, facture)
        self.assertEqual(regularisation.etat, 'facturee')

    def test_ecart_negatif_cree_un_avoir_jamais_de_total_negatif(self):
        """Σ écarts négatif -> avoir (out_refund) ; le total reste positif même
        quand des lignes individuelles varient en sens opposé."""
        regularisation = self._regularisation(
            self.souscription_base,
            [
                {'cadran': 'base', 'ecart_kwh': 50.0, 'prix_kwh': 0.10, 'detail': 'Janvier 2024 : 50.00 kWh'},
                {'cadran': 'base', 'ecart_kwh': -100.0, 'prix_kwh': 0.10, 'detail': 'Février 2024 : -100.00 kWh'},
            ],
        )
        self.assertLess(regularisation.montant_total, 0.0)

        facture = regularisation._creer_facture()

        self.assertEqual(facture.move_type, 'out_refund')
        self.assertAlmostEqual(facture.amount_untaxed, 5.0, places=2)  # |5.0 - 10.0|
        self.assertGreater(facture.amount_total, 0.0)

    def test_une_ligne_par_grille_cadran_avec_notes_par_mois(self):
        """Une ligne produit par (grille, cadran) ; sous chacune, une note par
        mois agrégé (mois + écart kWh, traçabilité gelée dans le document légal)."""
        regularisation = self._regularisation(
            self.souscription_hphc,
            [
                {
                    'cadran': 'hp',
                    'ecart_kwh': 30.0,
                    'prix_kwh': 0.18,
                    'detail': 'Janvier 2024 : 20.00 kWh\nFévrier 2024 : 10.00 kWh',
                },
                {'cadran': 'hc', 'ecart_kwh': 15.0, 'prix_kwh': 0.12, 'detail': 'Janvier 2024 : 15.00 kWh'},
            ],
        )

        facture = regularisation._creer_facture()

        lignes_produit = facture.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
        self.assertEqual(len(lignes_produit), 2, 'une ligne par grille × cadran')

        notes = facture.invoice_line_ids.filtered(lambda l: l.display_type == 'line_note')
        self.assertEqual(len(notes), 3, 'une note par mois agrégé (2 + 1)')
        noms = notes.mapped('name')
        self.assertIn('Janvier 2024 : 20.00 kWh', noms)
        self.assertIn('Février 2024 : 10.00 kWh', noms)
        self.assertIn('Janvier 2024 : 15.00 kWh', noms)

    def test_produit_resolu_par_catalogue_solidaire_isole(self):
        """Le produit (donc le compte/la TVA) vient du catalogue, choisi par
        le cadran ET le tarif solidaire (ADR 0013) — isolation respectée."""
        regularisation = self._regularisation(
            self.souscription_base,
            [{'cadran': 'base', 'ecart_kwh': 40.0, 'prix_kwh': 0.15, 'tarif_solidaire': True, 'detail': ''}],
        )

        facture = regularisation._creer_facture()

        ligne_produit = facture.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
        produit_solidaire = self.env['souscription.produit'].produit_energie('base', is_solidaire=True)
        produit_standard = self.env['souscription.produit'].produit_energie('base', is_solidaire=False)
        self.assertEqual(ligne_produit.product_id, produit_solidaire)
        self.assertNotEqual(ligne_produit.product_id, produit_standard)

    def test_aucune_ligne_leve_usererror(self):
        """Rien à facturer : refus explicite plutôt qu'une Facture vide."""
        regularisation = self.env['souscription.regularisation'].create({'souscription_id': self.souscription_base.id})
        with self.assertRaises(UserError):
            regularisation._creer_facture()

    def test_creer_facture_marque_facturee_et_refuse_une_seconde_facture(self):
        regularisation = self._regularisation(
            self.souscription_base,
            [{'cadran': 'base', 'ecart_kwh': 20.0, 'prix_kwh': 0.15, 'detail': 'Janvier 2024 : 20.00 kWh'}],
        )

        regularisation._creer_facture()

        self.assertEqual(regularisation.etat, 'facturee')
        with self.assertRaises(UserError):
            regularisation._creer_facture()


@tagged('souscriptions', 'souscriptions_regularisation', 'souscriptions_cheque_energie', 'post_install', '-at_install')
class TestRegularisationFactureChequeEnergie(SouscriptionsTestCase):
    """#172 : imputation FIFO du chèque énergie validé sur la facture de
    régularisation, même mécanique que la mensuelle (test_periode_facture.py).
    Déplacée de la création à l'ÉMISSION (tranche 1 du PRD #264, #265) :
    `_creer_facture()` ne produit qu'un brouillon, l'imputation se déclenche
    à `action_post()`."""

    def _new_cheque(self, **kwargs):
        vals = {
            'numero': 'CHQ-REGUL-A',
            'partner_id': self.partner_test.id,
            'montant': 10.0,
            'date_reception': date(2024, 1, 5),
            'date_expiration': date(2025, 3, 31),
        }
        vals.update(kwargs)
        return self.env['souscription.cheque_energie'].create(vals)

    def _regularisation_avec_ecart(self, montant_ecart=50.0):
        regularisation = self.env['souscription.regularisation'].create(
            {
                'souscription_id': self.souscription_base.id,
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 2, 1),
            }
        )
        self.env['souscription.regularisation.ligne'].create(
            {
                'regularisation_id': regularisation.id,
                'grille_id': self.grille_prix.id,
                'cadran': 'base',
                'ecart_kwh': montant_ecart,
                'prix_kwh': 0.15,
                'detail': 'Janvier 2024 : 50.00 kWh',
            }
        )
        return regularisation

    def test_creation_avec_cheque_valide_reste_en_brouillon(self):
        """AC #265, transposé à la régularisation : la création reste un
        brouillon même avec un chèque validé disponible."""
        cheque = self._new_cheque(montant=5.0)
        cheque.action_valider()

        regularisation = self._regularisation_avec_ecart()
        facture = regularisation._creer_facture()

        self.assertEqual(facture.state, 'draft')
        self.assertAlmostEqual(cheque.solde, cheque.montant, places=2, msg='rien imputé avant émission')

    def test_cheque_valide_reduit_amount_residual_de_la_facture_de_regularisation(self):
        cheque = self._new_cheque(montant=5.0)
        cheque.action_valider()

        regularisation = self._regularisation_avec_ecart()
        facture = regularisation._creer_facture()
        self.assertEqual(facture.state, 'draft')

        facture.action_post()

        self.assertEqual(facture.state, 'posted')
        self.assertAlmostEqual(facture.amount_residual, facture.amount_total - 5.0, places=2)
        self.assertAlmostEqual(cheque.solde, 0.0, places=2)


@tagged(
    'souscriptions', 'souscriptions_facture_document', 'souscriptions_regularisation', 'post_install', '-at_install'
)
class TestRegularisationFactureDocument(SouscriptionsTestMixin, HttpCase):
    """PDF/HTML de la facture de régularisation — variante du template mensuel
    (test_facture_document.py) : bloc justificatif bi-parent, relevés portés
    par la Régularisation elle-même (ADR 0030 décision 5)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        regularisation = cls.env['souscription.regularisation'].create(
            {
                'souscription_id': cls.souscription_base.id,
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 2, 1),
            }
        )
        cls.env['souscription.regularisation.ligne'].create(
            {
                'regularisation_id': regularisation.id,
                'grille_id': cls.grille_prix.id,
                'cadran': 'base',
                'ecart_kwh': 50.0,
                'prix_kwh': 0.15,
                'detail': 'Janvier 2024 : 50.00 kWh',
            }
        )
        cls.env['souscription.releve'].create(
            {
                'regularisation_id': regularisation.id,
                'date': date(2024, 1, 31),
                'nature': 'reel',
                'index_base': 91234,
            }
        )
        cls.regularisation_test = regularisation
        cls.facture_test = regularisation._creer_facture()

    def test_facture_regularisation_pdf(self):
        """Le PDF se génère sans erreur, justificatif des relevés frais compris."""
        self.authenticate('admin', 'admin')
        response = self.url_open(PDF_URL % self.facture_test.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Content-Type'), 'application/pdf')
        self.assertGreater(len(response.content), 1000)

    def test_facture_regularisation_html_porte_le_justificatif_biparent(self):
        """Le bloc justificatif rend les relevés de la Régularisation
        (bi-parent, pas ceux d'une Période — il n'y en a aucune ici)."""
        self.authenticate('admin', 'admin')
        response = self.url_open(HTML_URL % self.facture_test.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Justificatif de calcul', response.text)
        self.assertIn('91234', response.text)  # index du relevé de la Régularisation
        self.assertIn('Janvier 2024 : 50.00 kWh', response.text)  # note par mois de la ligne
