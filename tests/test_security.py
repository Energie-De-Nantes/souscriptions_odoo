"""Tests des droits d'accès : groupes utilisateur / gestionnaire."""

from datetime import date

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged

from .common import SouscriptionsTestMixin


@tagged('souscriptions', 'souscriptions_security', 'post_install', '-at_install')
class TestSouscriptionsSecurity(SouscriptionsTestMixin, TransactionCase):
    """Vérifie que les deux niveaux de droits sont effectivement appliqués."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()

        cls.user = cls.env['res.users'].create(
            {
                'name': 'Souscriptions User',
                'login': 'souscriptions_user',
                'email': 'user@souscriptions.test',
                'group_ids': [
                    (
                        6,
                        0,
                        [
                            cls.env.ref('souscriptions_odoo.group_souscriptions_user').id,
                        ],
                    )
                ],
            }
        )
        cls.manager = cls.env['res.users'].create(
            {
                'name': 'Souscriptions Manager',
                'login': 'souscriptions_manager',
                'email': 'manager@souscriptions.test',
                'group_ids': [
                    (
                        6,
                        0,
                        [
                            cls.env.ref('souscriptions_odoo.group_souscriptions_manager').id,
                        ],
                    )
                ],
            }
        )

    def _new_souscription(self):
        return self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner_test.id,
                'pdl': 'PDL_SEC',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'etat_facturation_id': self.etat_facturation.id,
                'date_debut': date(2024, 1, 1),
            }
        )

    # --- Utilisateur standard : lecture/écriture mais pas de suppression ---

    def test_user_can_read_and_write_souscription(self):
        sous = self.souscription_base.with_user(self.user)
        sous.read(['name'])
        sous.write({'numero_depannage': '09 999'})  # ne doit pas lever

    def test_user_cannot_unlink_souscription(self):
        sous = self._new_souscription()
        with self.assertRaises(AccessError):
            sous.with_user(self.user).unlink()

    def test_user_cannot_unlink_periode(self):
        periode = self.create_test_periode(self.souscription_base)
        with self.assertRaises(AccessError):
            periode.with_user(self.user).unlink()

    def test_user_can_read_but_not_write_grille(self):
        grille = self.grille_prix.with_user(self.user)
        grille.read(['name'])  # lecture autorisée
        with self.assertRaises(AccessError):
            grille.write({'name': 'Tentative interdite'})

    def test_user_cannot_create_grille(self):
        with self.assertRaises(AccessError):
            self.env['grille.prix'].with_user(self.user).create(
                {
                    'name': 'Grille interdite',
                    'date_debut': date(2025, 1, 1),
                }
            )

    # --- Gestionnaire : tous les droits ---

    def test_manager_can_unlink_souscription(self):
        sous = self._new_souscription()
        sous.with_user(self.manager).unlink()
        self.assertFalse(sous.exists())

    def test_manager_can_write_grille(self):
        self.grille_prix.with_user(self.manager).write({'name': 'Renommée par manager'})
        self.assertEqual(self.grille_prix.name, 'Renommée par manager')

    def test_manager_can_create_grille(self):
        grille = (
            self.env['grille.prix']
            .with_user(self.manager)
            .create(
                {
                    'name': 'Grille manager',
                    'date_debut': date(2025, 6, 1),
                }
            )
        )
        self.assertTrue(grille.exists())
