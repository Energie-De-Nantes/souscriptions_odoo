"""Tests de la vue « Règlements en attente » (#185, PRD #183).

Le *Mode de paiement* est porté par la Souscription (source de vérité unique,
CONTEXT.md) ; la Facture ne fait que le refléter en related stocké — jamais
saisi sur la facture. L'action de menu liste les factures d'énergie postées à
reste-à-payer > 0 dont le mode diffère de `prelevement`, groupe « (vide) »
compris (souscription sans mode renseigné — à compléter, pas à deviner).
"""

import ast

from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_paiements', 'post_install', '-at_install')
class TestFactureModePaiementRelated(SouscriptionsTestCase):
    def test_mode_paiement_suit_la_souscription(self):
        """related stocké : reflète le mode courant de la Souscription."""
        self.souscription_base.mode_paiement = 'virement'
        periode, facture = self.create_test_invoice(self.souscription_base)
        self.assertEqual(facture.mode_paiement, 'virement')

    def test_mode_paiement_suit_les_changements_ulterieurs(self):
        """Un related stocké se recalcule quand la source change (pas une
        copie figée à la création)."""
        self.souscription_base.mode_paiement = 'virement'
        periode, facture = self.create_test_invoice(self.souscription_base)

        self.souscription_base.mode_paiement = 'especes'

        self.assertEqual(facture.mode_paiement, 'especes')

    def test_facture_sans_souscription_mode_paiement_vide(self):
        """Une facture hors énergie (pas de periode_id/souscription_id) a un
        mode de paiement vide — pas de valeur devinée."""
        facture = self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': self.partner_test.id,
            }
        )
        self.assertFalse(facture.mode_paiement)


@tagged('souscriptions', 'souscriptions_paiements', 'post_install', '-at_install')
class TestActionReglementsEnAttente(SouscriptionsTestCase):
    def _facture_posted(self, mode_paiement, **periode_kwargs):
        if mode_paiement is not None:
            self.souscription_base.mode_paiement = mode_paiement
        periode, facture = self.create_test_invoice(self.souscription_base, **periode_kwargs)
        facture.action_post()
        return facture

    def _domaine_action(self):
        action = self.env.ref('souscriptions_odoo.action_facture_reglements_attente')
        return ast.literal_eval(action.domain)

    def _dans_la_vue(self, facture):
        domaine = self._domaine_action()
        return facture in self.env['account.move'].search(domaine + [('id', '=', facture.id)])

    def test_facture_prelevement_exclue(self):
        facture = self._facture_posted('prelevement')
        self.assertFalse(self._dans_la_vue(facture), 'le prélèvement a son propre circuit (#186)')

    def test_facture_virement_incluse(self):
        facture = self._facture_posted('virement')
        self.assertTrue(self._dans_la_vue(facture))

    def test_facture_mode_vide_incluse_groupe_vide(self):
        """Souscription sans mode renseigné : apparaît (groupe « (vide) »,
        à compléter par la facturiste, jamais deviné)."""
        facture = self._facture_posted(None)
        self.assertFalse(facture.souscription_id.mode_paiement)
        self.assertTrue(self._dans_la_vue(facture))

    def test_facture_brouillon_exclue(self):
        self.souscription_base.mode_paiement = 'virement'
        periode, facture = self.create_test_invoice(self.souscription_base)
        self.assertEqual(facture.state, 'draft')
        self.assertFalse(self._dans_la_vue(facture))

    def test_facture_soldee_exclue(self):
        """Reste-à-payer nul (ex. chèque énergie couvrant tout) : sort du
        domaine d'elle-même — pas de code dédié pour cette exigence."""
        facture = self._facture_posted('virement')
        self.assertGreater(facture.amount_residual, 0.0)

        journal = self.env['account.journal'].search([('type', '=', 'bank')], limit=1)
        wizard = (
            self.env['account.payment.register']
            .with_context(active_model='account.move', active_ids=facture.ids)
            .create({'journal_id': journal.id})
        )
        wizard._create_payments()
        facture.invalidate_recordset(['amount_residual'])

        self.assertAlmostEqual(facture.amount_residual, 0.0, places=2)
        self.assertFalse(self._dans_la_vue(facture), 'un paiement natif enregistré fait sortir la facture de la vue')

    def test_menu_reglements_en_attente(self):
        menu = self.env.ref('souscriptions_odoo.menu_facture_reglements_attente')
        self.assertEqual(menu.parent_id, self.env.ref('souscriptions_odoo.menu_souscription_root'))
        action = self.env.ref('souscriptions_odoo.action_facture_reglements_attente')
        self.assertEqual(menu.action.id, action.id)
        self.assertEqual(action.res_model, 'account.move')
