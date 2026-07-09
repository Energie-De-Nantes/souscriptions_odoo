"""
Tests du lien Période ↔ Facture (issue #23 / ADR 0004).

`account.move.periode_id` est l'unique source de vérité du lien : la période
expose sa facture via `facture_id`, champ calculé/stocké dérivé de ce lien.
"""

from datetime import date

from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_periode_facture', 'post_install', '-at_install')
class TestPeriodeFactureLien(SouscriptionsTestCase):
    def test_facture_id_derive_du_periode_id(self):
        """facture_id reflète le account.move qui pointe la période via periode_id."""
        periode = self.create_test_periode(self.souscription_base)
        self.assertFalse(periode.facture_id, 'Aucune facture liée au départ')

        facture = self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': self.partner_test.id,
                'invoice_date': date(2024, 2, 5),
                'periode_id': periode.id,
            }
        )

        self.assertEqual(periode.facture_id, facture)

    def test_facture_ids_souscription_agrege_les_periodes(self):
        """souscription.facture_ids agrège automatiquement les factures des périodes."""
        periode = self.create_test_periode(self.souscription_base)
        facture = periode._creer_facture()
        self.assertIn(facture, self.souscription_base.facture_ids)

    def test_creer_factures_ne_double_pas(self):
        """creer_factures est idempotent : une seule facture par période (anti-doublon)."""
        self.create_test_periode(self.souscription_base, date_debut=date(2024, 1, 1), date_fin=date(2024, 1, 31))

        self.souscription_base.creer_factures()
        self.assertEqual(len(self.souscription_base.facture_ids), 1)

        # Second appel : aucune facture supplémentaire ne doit être créée.
        self.souscription_base.creer_factures()
        self.assertEqual(len(self.souscription_base.facture_ids), 1)


@tagged('souscriptions', 'souscriptions_periode_facture', 'souscriptions_cheque_energie', 'post_install', '-at_install')
class TestPeriodeFactureChequeEnergie(SouscriptionsTestCase):
    """#172, couture 2 (point de couture le plus haut) : effet de l'imputation
    FIFO des chèques énergie validés sur `amount_residual`, au hook
    `_creer_facture()` (ADR 0026)."""

    def _new_cheque(self, **kwargs):
        vals = {
            'numero': 'CHQ-172-A',
            'partner_id': self.partner_test.id,
            'montant': 10.0,
            'date_reception': date(2024, 1, 5),
            'date_expiration': date(2025, 3, 31),
        }
        vals.update(kwargs)
        return self.env['souscription.cheque_energie'].create(vals)

    def test_cheque_valide_reduit_amount_residual_sans_jamais_etre_negatif(self):
        """Facture couverte partiellement par un chèque validé : amount_residual
        réduit de min(solde, total), jamais négatif."""
        cheque = self._new_cheque(montant=10.0)
        cheque.action_valider()

        periode = self.create_test_periode(self.souscription_base)
        facture = periode._creer_facture()

        self.assertEqual(facture.state, 'posted')
        self.assertAlmostEqual(facture.amount_residual, facture.amount_total - 10.0, places=2)
        self.assertGreaterEqual(facture.amount_residual, 0.0)
        self.assertAlmostEqual(cheque.solde, 0.0, places=2)

    def test_cheque_non_valide_aucun_effet(self):
        """Un chèque 'reçu' (non validé) n'impute rien : la Facture reste
        `draft`, amount_residual == amount_total, comme sans chèque du tout."""
        self._new_cheque(montant=1000.0)  # jamais validé

        periode = self.create_test_periode(self.souscription_base)
        facture = periode._creer_facture()

        self.assertEqual(facture.state, 'draft')
        self.assertAlmostEqual(facture.amount_residual, facture.amount_total, places=2)

    def test_fifo_par_expiration_le_plus_proche_consomme_en_premier(self):
        """Deux chèques validés : celui qui périme le plus tôt est consommé en
        premier (FIFO par expiration), quel que soit l'ordre de création/montant."""
        cheque_tardif = self._new_cheque(numero='CHQ-172-TARD', montant=1000.0, date_expiration=date(2026, 3, 31))
        cheque_tardif.action_valider()
        cheque_proche = self._new_cheque(numero='CHQ-172-PROCHE', montant=5.0, date_expiration=date(2024, 3, 31))
        cheque_proche.action_valider()

        periode = self.create_test_periode(self.souscription_base)
        facture = periode._creer_facture()

        # Le chèque qui périme le plus tôt (proche) est épuisé en premier ;
        # le tardif n'absorbe que ce que le proche n'a pas couvert.
        self.assertAlmostEqual(cheque_proche.solde, 0.0, places=2)
        self.assertAlmostEqual(
            cheque_tardif.solde,
            cheque_tardif.montant - (facture.amount_total - cheque_proche.montant),
            places=2,
        )
        self.assertAlmostEqual(facture.amount_residual, 0.0, places=2)

    def test_reliquat_se_reporte_sur_la_facture_suivante(self):
        """Un chèque plus gros qu'une Facture se reporte sur la Facture suivante
        jusqu'à épuisement — report natif du lettrage, pas de code métier."""
        cheque = self._new_cheque(montant=1000.0)
        cheque.action_valider()

        periode_janvier = self.create_test_periode(
            self.souscription_base, date_debut=date(2024, 1, 1), date_fin=date(2024, 1, 31)
        )
        facture_janvier = periode_janvier._creer_facture()
        self.assertAlmostEqual(facture_janvier.amount_residual, 0.0, places=2)
        solde_apres_janvier = cheque.solde
        self.assertGreater(solde_apres_janvier, 0.0)

        periode_fevrier = self.create_test_periode(
            self.souscription_base, date_debut=date(2024, 2, 1), date_fin=date(2024, 2, 29)
        )
        facture_fevrier = periode_fevrier._creer_facture()

        self.assertAlmostEqual(facture_fevrier.amount_residual, 0.0, places=2)
        self.assertAlmostEqual(cheque.solde, solde_apres_janvier - facture_fevrier.amount_total, places=2)

    def test_structure_facture_et_pas_de_ligne_negative(self):
        """Tiers-payeur, jamais une remise (ADR 0026) : la structure de la
        Facture (sections, notes TURPE, lignes produit) et son CA/TVA ne sont
        pas touchés par l'imputation — aucune ligne négative n'est ajoutée."""
        cheque = self._new_cheque(montant=10.0)
        cheque.action_valider()

        periode = self.create_test_periode(self.souscription_base)
        facture = periode._creer_facture()

        self.assert_invoice_structure(facture)
        lignes_produit = facture.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
        self.assertTrue(lignes_produit)
        self.assertTrue(all(l.quantity >= 0 and l.price_unit >= 0 for l in lignes_produit))
        self.assertAlmostEqual(facture.amount_untaxed, sum(lignes_produit.mapped('price_subtotal')), places=2)
