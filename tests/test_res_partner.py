"""
Tests du champ blaze sur le partenaire (#106, ADR 0023).

Champ d'atterrissage migration : nom d'usage choisi par le·la
souscripteur·rice, distinct du nom légal (`name`) — repris de `x_blaze`
(prod, ~357 cartes du kanban de raccordement portent la valeur).
"""

from odoo.tests.common import TransactionCase, tagged


@tagged('souscriptions', 'post_install', '-at_install')
class TestResPartnerBlaze(TransactionCase):
    def test_blaze_creation(self):
        """Le champ blaze se crée et se lit tel quel."""
        partner = self.env['res.partner'].create(
            {
                'name': 'Test Client',
                'blaze': 'Titi',
            }
        )

        self.assertEqual(partner.blaze, 'Titi')

    def test_blaze_visible_sur_le_formulaire(self):
        """Le champ blaze est exposé au formulaire partenaire (#106)."""
        view = self.env['res.partner'].get_view(view_type='form')
        self.assertIn('blaze', view['arch'])
