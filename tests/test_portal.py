"""
Tests du portail usager·ère (#24) : l'historique des consommations est intégré
directement dans la page de détail d'une souscription. Seules les périodes dont
la facture est émise (postée) sont visibles ; il n'y a plus de page /periodes.
"""

from odoo.tests.common import HttpCase, tagged
from odoo.addons.souscriptions_odoo.tests.common import SouscriptionsTestMixin
from datetime import date


@tagged('post_install', '-at_install', 'portal')
class PortalTestCase(SouscriptionsTestMixin, HttpCase):
    """Tests du portail usager·ère pour les souscriptions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()

        cls.portal_user = cls.env['res.users'].create({
            'name': 'Portal Test User',
            'login': 'portal_test',
            'email': 'portal@test.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_portal').id])],
        })
        cls.partner_test.user_ids = [(6, 0, [cls.portal_user.id])]

        cls._create_periods_and_posted_invoices()

    @classmethod
    def _create_periods_and_posted_invoices(cls):
        """Deux périodes facturées et POSTÉES (donc visibles côté portail)."""
        cls.periode_jan = cls.env['souscription.periode'].create({
            'souscription_id': cls.souscription_base.id,
            'date_debut': date(2024, 1, 1), 'date_fin': date(2024, 1, 31),
            'type_periode': 'mensuelle',
            'energie_base_kwh': 280.0, 'provision_base_kwh': 300.0,
            'turpe_fixe': 8.50, 'turpe_variable': 12.30,
        })
        cls.periode_feb = cls.env['souscription.periode'].create({
            'souscription_id': cls.souscription_base.id,
            'date_debut': date(2024, 2, 1), 'date_fin': date(2024, 2, 29),
            'type_periode': 'mensuelle',
            'energie_base_kwh': 320.0, 'provision_base_kwh': 300.0,
            'turpe_fixe': 8.50, 'turpe_variable': 14.20,
        })
        cls.facture_jan = cls.souscription_base._creer_facture_periode(cls.periode_jan)
        cls.facture_feb = cls.souscription_base._creer_facture_periode(cls.periode_feb)
        (cls.facture_jan | cls.facture_feb).action_post()

    @classmethod
    def _facture_postee_simple(cls, souscription, periode, invoice_date):
        """Facture postée minimale (sans dépendre d'une grille de prix)."""
        produit = cls.env.ref('souscriptions_odoo.souscriptions_product_energie_base')
        move = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': souscription.partner_id.id,
            'invoice_date': invoice_date,
            'periode_id': periode.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': produit.id, 'quantity': 1, 'price_unit': 10.0,
            })],
        })
        move.action_post()
        return move

    def _detail_url(self, souscription=None):
        souscription = souscription or self.souscription_base
        return f'/my/souscription/{souscription.id}'

    # --- Accès ---

    def test_acces_non_authentifie_redirige_login(self):
        """Accès non authentifié à la liste et au détail : redirection login."""
        for url in ('/my/souscriptions', self._detail_url()):
            response = self.url_open(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn('login', response.url)

    def test_liste_souscriptions_authentifie(self):
        """La liste des souscriptions montre la souscription de l'usager."""
        self.authenticate(self.portal_user.login, self.portal_user.login)
        response = self.url_open('/my/souscriptions')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.souscription_base.name, response.text)
        self.assertIn(self.souscription_base.pdl, response.text)

    # --- Historique intégré ---

    def test_detail_affiche_historique_inline_sans_bouton(self):
        """L'historique est dans la page ; l'ancien bouton de navigation a disparu."""
        self.authenticate(self.portal_user.login, self.portal_user.login)
        response = self.url_open(self._detail_url())
        self.assertEqual(response.status_code, 200)

        self.assertIn(self.souscription_base.pdl, response.text)
        self.assertIn('Historique des consommations', response.text)
        # le bouton vers l'ancienne page séparée n'existe plus
        self.assertNotIn("Voir l'historique des consommations", response.text)
        # les périodes facturées (postées) sont listées, avec leur facture
        self.assertIn(self.facture_jan.name, response.text)
        self.assertIn(self.facture_feb.name, response.text)

    def test_seules_periodes_facture_postee_visibles(self):
        """Une période dont la facture est en brouillon n'apparaît pas."""
        periode_draft = self.env['souscription.periode'].create({
            'souscription_id': self.souscription_base.id,
            'date_debut': date(2024, 3, 1), 'date_fin': date(2024, 3, 31),
            'type_periode': 'mensuelle',
            'energie_base_kwh': 999.0, 'turpe_fixe': 1.0, 'turpe_variable': 1.0,
        })
        facture_draft = self.souscription_base._creer_facture_periode(periode_draft)
        self.assertEqual(facture_draft.state, 'draft')

        self.authenticate(self.portal_user.login, self.portal_user.login)
        response = self.url_open(self._detail_url())
        self.assertEqual(response.status_code, 200)
        # l'énergie spécifique de la période en brouillon ne doit pas fuiter
        self.assertNotIn('999', response.text)

    def test_route_periodes_supprimee(self):
        """L'ancienne page /periodes n'existe plus (404)."""
        self.authenticate(self.portal_user.login, self.portal_user.login)
        response = self.url_open(self._detail_url() + '/periodes')
        self.assertEqual(response.status_code, 404)

    def test_colonnes_energie_selon_type_tarif(self):
        """Les colonnes énergie s'adaptent au type de tarif (Base vs HP/HC)."""
        self.authenticate(self.portal_user.login, self.portal_user.login)

        # Base
        response = self.url_open(self._detail_url())
        self.assertIn('Énergie Base (kWh)', response.text)
        self.assertNotIn('Énergie HP (kWh)', response.text)

        # HP/HC
        self.souscription_hphc.partner_id = self.partner_test.id
        periode_hphc = self.env['souscription.periode'].create({
            'souscription_id': self.souscription_hphc.id,
            'date_debut': date(2024, 1, 1), 'date_fin': date(2024, 1, 31),
            'type_periode': 'mensuelle',
            'energie_hph_kwh': 120.0, 'energie_hpb_kwh': 80.0,
            'energie_hch_kwh': 70.0, 'energie_hcb_kwh': 50.0,
            'turpe_fixe': 12.80, 'turpe_variable': 18.50,
        })
        self.souscription_hphc._creer_facture_periode(periode_hphc).action_post()

        response = self.url_open(self._detail_url(self.souscription_hphc))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Énergie HP (kWh)', response.text)
        self.assertIn('Énergie HC (kWh)', response.text)
        self.assertNotIn('Énergie Base (kWh)', response.text)

    def test_totaux_affiches(self):
        """La carte Totaux est présente et somme les périodes facturées."""
        self.authenticate(self.portal_user.login, self.portal_user.login)
        response = self.url_open(self._detail_url())
        self.assertEqual(response.status_code, 200)

        self.assertIn('Consommation totale', response.text)
        self.assertIn('TURPE total', response.text)
        self.assertIn('Total facturé', response.text)

        total_kwh = self.periode_jan.energie_base_kwh + self.periode_feb.energie_base_kwh
        self.assertIn(f'{total_kwh:.0f}', response.text)

    def test_etat_vide_sans_facture_postee(self):
        """Une souscription sans période facturée affiche un état vide propre."""
        empty = self.env['souscription.souscription'].create({
            'partner_id': self.partner_test.id,
            'pdl': 'PDL_EMPTY_TEST', 'puissance_souscrite': '6',
            'type_tarif': 'base', 'etat_facturation_id': self.etat_facturation.id,
        })
        self.authenticate(self.portal_user.login, self.portal_user.login)
        response = self.url_open(self._detail_url(empty))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Aucune période facturée', response.text)

    def test_voir_plus_au_dela_de_douze(self):
        """Au-delà de 12 périodes facturées, un bouton « Voir plus » apparaît."""
        for mois in range(1, 12):  # 11 périodes supplémentaires -> 13 au total
            periode = self.env['souscription.periode'].create({
                'souscription_id': self.souscription_base.id,
                'date_debut': date(2023, mois, 1),
                'date_fin': date(2023, mois, 28),
                'type_periode': 'mensuelle',
                'energie_base_kwh': 100.0 + mois,
                'turpe_fixe': 5.0, 'turpe_variable': 2.0,
            })
            self._facture_postee_simple(
                self.souscription_base, periode, date(2023, mois, 28))

        self.authenticate(self.portal_user.login, self.portal_user.login)
        response = self.url_open(self._detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertIn('Voir plus', response.text)

    def test_securite_autre_usager(self):
        """Un usager ne peut pas voir la souscription d'un autre (403)."""
        other_partner = self.env['res.partner'].create({
            'name': 'Other User', 'email': 'other@test.com'})
        other_user = self.env['res.users'].create({
            'name': 'Other Portal User', 'login': 'other_portal',
            'email': 'other_portal@test.com',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        other_partner.user_ids = [(6, 0, [other_user.id])]
        other_souscription = self.env['souscription.souscription'].create({
            'partner_id': other_partner.id, 'pdl': 'PDL_OTHER_USER',
            'puissance_souscrite': '3', 'type_tarif': 'base',
            'etat_facturation_id': self.etat_facturation.id,
        })

        self.authenticate(self.portal_user.login, self.portal_user.login)
        response = self.url_open(self._detail_url(other_souscription))
        self.assertEqual(response.status_code, 403)


@tagged('post_install', '-at_install', 'portal_integration')
class PortalIntegrationTestCase(SouscriptionsTestMixin, HttpCase):
    """Tests d'intégration du portail avec le reste du système."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()

    def test_portal_menu_integration(self):
        """L'entrée du portail (tuile d'accueil) existe."""
        portal_menu = self.env.ref(
            'souscriptions_odoo.portal_my_home_souscriptions', raise_if_not_found=False)
        self.assertTrue(portal_menu, "Le menu portal doit exister")

    def test_facture_postee_apparait_dans_historique(self):
        """Une facture réelle postée apparaît dans l'historique intégré."""
        periode, facture = self.create_test_invoice(self.souscription_base)
        facture.action_post()
        self.souscription_base.partner_id = self.partner_test.id

        portal_user = self.env['res.users'].create({
            'name': 'Integration Test User', 'login': 'integration_test',
            'email': 'integration@test.com',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        self.partner_test.user_ids = [(6, 0, [portal_user.id])]
        self.authenticate(portal_user.login, portal_user.login)

        response = self.url_open(f'/my/souscription/{self.souscription_base.id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(facture.name, response.text)

    def test_portal_permissions_consistency(self):
        """Les droits portail (lecture seule) sont cohérents."""
        portal_group = self.env.ref('base.group_portal')

        access = self.env['ir.model.access'].search([
            ('model_id.model', '=', 'souscription.souscription'),
            ('group_id', '=', portal_group.id),
        ])
        self.assertTrue(access, "Accès portal aux souscriptions requis")
        self.assertTrue(access.perm_read, "Lecture autorisée")
        self.assertFalse(access.perm_write, "Écriture interdite")
        self.assertFalse(access.perm_create, "Création interdite")
        self.assertFalse(access.perm_unlink, "Suppression interdite")

        access = self.env['ir.model.access'].search([
            ('model_id.model', '=', 'souscription.periode'),
            ('group_id', '=', portal_group.id),
        ])
        self.assertTrue(access, "Accès portal aux périodes requis")
        self.assertTrue(access.perm_read, "Lecture autorisée")
        self.assertFalse(access.perm_write, "Écriture interdite")
