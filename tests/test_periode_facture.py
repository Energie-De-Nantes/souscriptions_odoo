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
        facture = self.souscription_base._creer_facture_periode(periode)
        self.assertIn(facture, self.souscription_base.facture_ids)

    def test_creer_factures_ne_double_pas(self):
        """creer_factures est idempotent : une seule facture par période (anti-doublon)."""
        self.create_test_periode(self.souscription_base, date_debut=date(2024, 1, 1), date_fin=date(2024, 1, 31))

        self.souscription_base.creer_factures()
        self.assertEqual(len(self.souscription_base.facture_ids), 1)

        # Second appel : aucune facture supplémentaire ne doit être créée.
        self.souscription_base.creer_factures()
        self.assertEqual(len(self.souscription_base.facture_ids), 1)
