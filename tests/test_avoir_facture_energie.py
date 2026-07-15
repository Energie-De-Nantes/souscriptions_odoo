"""Observation : que fait l'avoir natif Odoo sur une facture d'énergie ?

Hypothèse à vérifier (grill C1) : `account.move.periode_id` n'a pas
`copy=False` (à la différence de `regularisation_id`, durci par le grill
#259), donc l'avoir produit par `_reverse_moves()` porte le lien vers la
Période. `_post()` filtre sur `is_facture_energie and state == 'draft'` — vrai
pour cet avoir — et le recompose depuis la Période.

Ces tests assertent le comportement SOUHAITÉ : un avoir est un document de
correction autonome, jamais une projection de la Période. S'ils échouent, le
suspect est réel.
"""

from datetime import date

from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_avoir', 'post_install', '-at_install')
class TestAvoirSurFactureEnergie(SouscriptionsTestCase):
    def _periode_facturee_emise(self):
        periode = self.create_test_periode(self.souscription_base, energie_base_kwh=280.0)
        facture = periode._creer_facture()
        facture.action_post()
        return periode, facture

    def test_avoir_ne_porte_pas_de_lignes_generees_en_double(self):
        """L'avoir reverse les lignes de la facture. Il ne doit pas, à
        l'émission, se voir AJOUTER une composition fraîche de la Période
        par-dessus."""
        periode, facture = self._periode_facturee_emise()
        lignes_facture = len(facture.invoice_line_ids)

        avoir = facture._reverse_moves([{'invoice_date': facture.invoice_date}])
        lignes_avoir_avant = len(avoir.invoice_line_ids)
        self.assertEqual(
            lignes_avoir_avant,
            lignes_facture,
            'le reverse copie les lignes une fois',
        )

        avoir.action_post()

        self.assertEqual(
            len(avoir.invoice_line_ids),
            lignes_avoir_avant,
            "l'émission de l'avoir ne doit rien recomposer depuis la Période",
        )

    def test_avoir_ne_rafle_pas_les_refacturations_en_file(self):
        """Une Refacturation « à refacturer » attend la prochaine facture. Un
        avoir sur une facture passée ne doit pas se l'approprier."""
        periode, facture = self._periode_facturee_emise()
        presta = self.env['souscription.refacturation'].create(
            {
                'souscription_id': self.souscription_base.id,
                'reference': 'REF-AVOIR-TEST-1',
                'libelle': 'Mise en service',
                'nature': 'prestation',
                'prix': 50.0,
                'quantite': 1.0,
            }
        )
        self.assertFalse(presta.facture_id, 'en file')

        avoir = facture._reverse_moves([{'invoice_date': facture.invoice_date}])
        avoir.action_post()

        self.assertFalse(
            presta.facture_id,
            "l'avoir ne doit pas rassembler les prestations en file",
        )

    def test_avoir_ne_consomme_pas_le_cheque_energie(self):
        """`_post` impute le chèque énergie sur le même filtre trop large
        (`is_facture_energie`). Un avoir rend de l'argent au·à la
        souscripteur·rice — il ne doit pas consommer le solde d'un chèque
        d'État, qui n'est pas un moyen de paiement mais un tiers-payeur."""
        periode, facture = self._periode_facturee_emise()
        cheque = self.env['souscription.cheque_energie'].create(
            {
                'numero': 'CHQ-AVOIR-1',
                'partner_id': self.partner_test.id,
                'montant': 1000.0,
                'date_reception': date(2024, 1, 5),
                'date_expiration': date(2025, 3, 31),
            }
        )
        cheque.action_valider()
        solde_avant = cheque.solde

        avoir = facture._reverse_moves([{'invoice_date': facture.invoice_date}])
        avoir.action_post()

        self.assertAlmostEqual(
            cheque.solde,
            solde_avant,
            places=2,
            msg="l'avoir ne doit pas consommer le chèque énergie",
        )

    def test_avoir_ne_devient_pas_la_facture_de_la_periode(self):
        """Le gel s'appuie sur `periode.facture_id` : l'avoir ne doit jamais
        le devenir, sinon le verrou de la Période sauterait."""
        periode, facture = self._periode_facturee_emise()

        avoir = facture._reverse_moves([{'invoice_date': facture.invoice_date}])
        avoir.action_post()

        self.assertEqual(periode.facture_id, facture, "la facture de la Période reste l'originale")
        self.assertTrue(periode._est_facturee_emise(), 'la Période reste gelée')
