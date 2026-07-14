"""
Tests du portail usager·ère (#24) : l'historique des consommations est intégré
directement dans la page de détail d'une souscription. Seules les périodes dont
la facture est émise (postée) sont visibles ; il n'y a plus de page /periodes.
"""

from datetime import date

from odoo.addons.souscriptions_odoo.tests.common import SouscriptionsTestMixin, build_grille_lignes
from odoo.tests.common import HttpCase, tagged


@tagged('post_install', '-at_install', 'portal')
class PortalTestCase(SouscriptionsTestMixin, HttpCase):
    """Tests du portail usager·ère pour les souscriptions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()

        cls.portal_user = cls.env['res.users'].create(
            {
                'name': 'Portal Test User',
                'login': 'portal_test',
                'email': 'portal@test.com',
                'group_ids': [(6, 0, [cls.env.ref('base.group_portal').id])],
            }
        )
        cls.partner_test.user_ids = [(6, 0, [cls.portal_user.id])]

        cls._create_periods_and_posted_invoices()

    @classmethod
    def _create_periods_and_posted_invoices(cls):
        """Deux périodes facturées et POSTÉES (donc visibles côté portail)."""
        cls.periode_jan = cls.env['souscription.periode'].create(
            {
                'souscription_id': cls.souscription_base.id,
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 1, 31),
                'type_periode': 'mensuelle',
                'energie_base_kwh': 280.0,
                'provision_base_kwh': 300.0,
                'turpe_fixe': 8.50,
                'turpe_variable': 12.30,
            }
        )
        cls.periode_feb = cls.env['souscription.periode'].create(
            {
                'souscription_id': cls.souscription_base.id,
                'date_debut': date(2024, 2, 1),
                'date_fin': date(2024, 2, 29),
                'type_periode': 'mensuelle',
                'energie_base_kwh': 320.0,
                'provision_base_kwh': 300.0,
                'turpe_fixe': 8.50,
                'turpe_variable': 14.20,
            }
        )
        cls.facture_jan = cls.periode_jan._creer_facture()
        cls.facture_feb = cls.periode_feb._creer_facture()
        (cls.facture_jan | cls.facture_feb).action_post()

    @classmethod
    def _facture_postee_simple(cls, souscription, periode, invoice_date):
        """Facture postée minimale. Depuis #266, l'émission recompose les
        lignes générées depuis la Période : une grille de prix doit couvrir
        `periode.date_fin` (la ligne bâtie ici, non flaguée, survit en
        manuelle)."""
        produit = cls.env.ref('souscriptions_odoo.souscriptions_product_energie_base')
        move = cls.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': souscription.partner_id.id,
                'invoice_date': invoice_date,
                'periode_id': periode.id,
                'invoice_line_ids': [
                    (
                        0,
                        0,
                        {
                            'product_id': produit.id,
                            'quantity': 1,
                            'price_unit': 10.0,
                        },
                    )
                ],
            }
        )
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

    def test_liste_reflete_le_statut_de_cycle_de_vie(self):
        """Le statut reflété au portail est l'état dérivé (`etat`, critère de
        #21, ADR 0031) — plus le générique « Active »/« Inactive » (archivage
        Odoo, sans rapport avec le cycle de vie)."""
        self.assertEqual(self.souscription_base.etat, 'en_instance')
        self.authenticate(self.portal_user.login, self.portal_user.login)
        response = self.url_open('/my/souscriptions')
        self.assertEqual(response.status_code, 200)
        self.assertIn('En instance', response.text)

    def test_apercu_via_access_token(self):
        """L'URL signée (access_token) ouvre la page à un non-propriétaire — c'est
        ce qui alimente le bouton « Aperçu » back-office. Sans token : 403."""
        autre_partner = self.env['res.partner'].create({'name': 'Autre', 'email': 'autre_apercu@test.com'})
        autre = self.env['souscription.souscription'].create(
            {
                'partner_id': autre_partner.id,
                'pdl': 'PDL_APERCU_TOKEN',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
            }
        )
        url = autre.get_portal_url()  # /my/souscription/<id>?access_token=...
        self.assertIn('access_token=', url)

        # portal_user n'est PAS le souscripteur d'`autre`
        self.authenticate(self.portal_user.login, self.portal_user.login)
        self.assertEqual(self.url_open(f'/my/souscription/{autre.id}').status_code, 403)
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('PDL_APERCU_TOKEN', response.text)

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
        periode_draft = self.env['souscription.periode'].create(
            {
                'souscription_id': self.souscription_base.id,
                'date_debut': date(2024, 3, 1),
                'date_fin': date(2024, 3, 31),
                'type_periode': 'mensuelle',
                'energie_base_kwh': 999.0,
                'turpe_fixe': 1.0,
                'turpe_variable': 1.0,
            }
        )
        facture_draft = periode_draft._creer_facture()
        self.assertEqual(facture_draft.state, 'draft')

        self.authenticate(self.portal_user.login, self.portal_user.login)
        response = self.url_open(self._detail_url())
        self.assertEqual(response.status_code, 200)
        # la période en brouillon (sa facture) ne doit pas apparaître ; on cible
        # le lien de sa facture (id), robuste contrairement à une sous-chaîne
        # numérique qui peut entrer en collision avec un hash de la page.
        self.assertNotIn(f'/my/invoices/{facture_draft.id}', response.text)

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
        periode_hphc = self.env['souscription.periode'].create(
            {
                'souscription_id': self.souscription_hphc.id,
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 1, 31),
                'type_periode': 'mensuelle',
                'energie_hph_kwh': 120.0,
                'energie_hpb_kwh': 80.0,
                'energie_hch_kwh': 70.0,
                'energie_hcb_kwh': 50.0,
                'turpe_fixe': 12.80,
                'turpe_variable': 18.50,
            }
        )
        periode_hphc._creer_facture().action_post()

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
        empty = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner_test.id,
                'pdl': 'PDL_EMPTY_TEST',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
            }
        )
        self.authenticate(self.portal_user.login, self.portal_user.login)
        response = self.url_open(self._detail_url(empty))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Aucune période facturée', response.text)

    def test_voir_plus_au_dela_de_douze(self):
        """Au-delà de 12 périodes facturées, un bouton « Voir plus » apparaît."""
        grille_2023 = self.env['grille.prix'].create(
            {
                'name': 'Grille Test 2023',
                'date_debut': date(2023, 1, 1),
                'date_fin': date(2023, 12, 31),
                'active': True,
            }
        )
        build_grille_lignes(self.env, grille_2023, prix_base=0.15, prix_hp=0.18, prix_hc=0.12)
        for mois in range(1, 12):  # 11 périodes supplémentaires -> 13 au total
            periode = self.env['souscription.periode'].create(
                {
                    'souscription_id': self.souscription_base.id,
                    'date_debut': date(2023, mois, 1),
                    'date_fin': date(2023, mois, 28),
                    'type_periode': 'mensuelle',
                    'energie_base_kwh': 100.0 + mois,
                    'turpe_fixe': 5.0,
                    'turpe_variable': 2.0,
                }
            )
            self._facture_postee_simple(self.souscription_base, periode, date(2023, mois, 28))

        self.authenticate(self.portal_user.login, self.portal_user.login)
        response = self.url_open(self._detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertIn('Voir plus', response.text)

    def test_securite_autre_usager(self):
        """Un usager ne peut pas voir la souscription d'un autre (403)."""
        other_partner = self.env['res.partner'].create({'name': 'Other User', 'email': 'other@test.com'})
        other_user = self.env['res.users'].create(
            {
                'name': 'Other Portal User',
                'login': 'other_portal',
                'email': 'other_portal@test.com',
                'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
            }
        )
        other_partner.user_ids = [(6, 0, [other_user.id])]
        other_souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': other_partner.id,
                'pdl': 'PDL_OTHER_USER',
                'puissance_souscrite': '3',
                'type_tarif': 'base',
            }
        )

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
        portal_menu = self.env.ref('souscriptions_odoo.portal_my_home_souscriptions', raise_if_not_found=False)
        self.assertTrue(portal_menu, 'Le menu portal doit exister')

    def test_facture_postee_apparait_dans_historique(self):
        """Une facture réelle postée apparaît dans l'historique intégré."""
        periode, facture = self.create_test_invoice(self.souscription_base)
        facture.action_post()
        self.souscription_base.partner_id = self.partner_test.id

        portal_user = self.env['res.users'].create(
            {
                'name': 'Integration Test User',
                'login': 'integration_test',
                'email': 'integration@test.com',
                'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
            }
        )
        self.partner_test.user_ids = [(6, 0, [portal_user.id])]
        self.authenticate(portal_user.login, portal_user.login)

        response = self.url_open(f'/my/souscription/{self.souscription_base.id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(facture.name, response.text)

    def test_portail_report_type_html_rend_le_design_energie(self):
        """Non-régression #289 : la page facture du portail encapsule le
        document dans une iframe pointant `invoice.get_portal_url(
        report_type='html')` (account/views/account_portal_templates.xml) —
        ce chemin doit rendre le design électricité (PDL), pas basculer sur
        le gabarit Odoo standard."""
        periode, facture = self.create_test_invoice(self.souscription_base)
        facture.action_post()
        self.souscription_base.partner_id = self.partner_test.id

        portal_user = self.env['res.users'].create(
            {
                'name': 'Portal HTML Test User',
                'login': 'portal_html_test',
                'email': 'portal_html@test.com',
                'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
            }
        )
        self.partner_test.user_ids = [(6, 0, [portal_user.id])]
        self.authenticate(portal_user.login, portal_user.login)

        response = self.url_open(f'/my/invoices/{facture.id}?report_type=html')
        self.assertEqual(response.status_code, 200)
        self.assertIn('PDL_TEST_STANDARD', response.text)

    def test_portal_permissions_consistency(self):
        """Les droits portail (lecture seule) sont cohérents."""
        portal_group = self.env.ref('base.group_portal')

        access = self.env['ir.model.access'].search(
            [
                ('model_id.model', '=', 'souscription.souscription'),
                ('group_id', '=', portal_group.id),
            ]
        )
        self.assertTrue(access, 'Accès portal aux souscriptions requis')
        self.assertTrue(access.perm_read, 'Lecture autorisée')
        self.assertFalse(access.perm_write, 'Écriture interdite')
        self.assertFalse(access.perm_create, 'Création interdite')
        self.assertFalse(access.perm_unlink, 'Suppression interdite')

        access = self.env['ir.model.access'].search(
            [
                ('model_id.model', '=', 'souscription.periode'),
                ('group_id', '=', portal_group.id),
            ]
        )
        self.assertTrue(access, 'Accès portal aux périodes requis')
        self.assertTrue(access.perm_read, 'Lecture autorisée')
        self.assertFalse(access.perm_write, 'Écriture interdite')


@tagged('post_install', '-at_install', 'portal', 'souscriptions_releve')
class PortalReleveTestCase(SouscriptionsTestMixin, HttpCase):
    """Bloc justificatif des relevés dans le détail souscription du portail
    (#57 / ADR 0015) : visible pour les périodes dont la facture est ÉMISE
    (postée) uniquement — un brouillon ne fuite jamais côté usager."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()

        cls.portal_user = cls.env['res.users'].create(
            {
                'name': 'Portal Releve User',
                'login': 'portal_releve',
                'email': 'portal_releve@test.com',
                'group_ids': [(6, 0, [cls.env.ref('base.group_portal').id])],
            }
        )
        cls.partner_test.user_ids = [(6, 0, [cls.portal_user.id])]

        # Période ÉMISE (postée) avec relevés saisis avant facturation.
        cls.periode_postee = cls.env['souscription.periode'].create(
            {
                'souscription_id': cls.souscription_base.id,
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 1, 31),
                'type_periode': 'mensuelle',
                'energie_base_kwh': 280.0,
                'turpe_fixe': 8.50,
                'turpe_variable': 12.30,
            }
        )
        cls.env['souscription.releve'].create(
            {'periode_id': cls.periode_postee.id, 'date': date(2024, 1, 1), 'nature': 'reel', 'index_base': 71000.0}
        )
        cls.env['souscription.releve'].create(
            {'periode_id': cls.periode_postee.id, 'date': date(2024, 1, 31), 'nature': 'estime', 'index_base': 71280.0}
        )
        cls.periode_postee._creer_facture().action_post()

        # Période en BROUILLON (facture non postée) avec un relevé : ne doit pas fuiter.
        cls.periode_brouillon = cls.env['souscription.periode'].create(
            {
                'souscription_id': cls.souscription_base.id,
                'date_debut': date(2024, 2, 1),
                'date_fin': date(2024, 2, 29),
                'type_periode': 'mensuelle',
                'energie_base_kwh': 300.0,
                'turpe_fixe': 8.50,
                'turpe_variable': 14.0,
            }
        )
        cls.env['souscription.releve'].create(
            {'periode_id': cls.periode_brouillon.id, 'date': date(2024, 2, 1), 'nature': 'reel', 'index_base': 99999.0}
        )
        cls.facture_brouillon = cls.periode_brouillon._creer_facture()  # reste draft

    def _detail_url(self):
        return f'/my/souscription/{self.souscription_base.id}'

    def test_releves_periode_emise_visibles(self):
        """Les relevés (date, nature, index) d'une période émise sont visibles."""
        self.authenticate(self.portal_user.login, self.portal_user.login)
        response = self.url_open(self._detail_url())
        self.assertEqual(response.status_code, 200)

        self.assertIn('71000', response.text)
        self.assertIn('71280', response.text)
        # Integer (#132) : rendu entier côté portail, pas de '.0' flottant.
        self.assertNotIn('71000.0', response.text)
        self.assertNotIn('71280.0', response.text)
        self.assertIn('Réel', response.text)
        self.assertIn('Estimé', response.text)

    def test_releves_periode_brouillon_ne_fuitent_pas(self):
        """Aucun relevé d'une période non émise (facture brouillon) n'apparaît."""
        self.assertEqual(self.facture_brouillon.state, 'draft')
        self.authenticate(self.portal_user.login, self.portal_user.login)
        response = self.url_open(self._detail_url())
        self.assertEqual(response.status_code, 200)

        self.assertNotIn('99999', response.text)


@tagged('post_install', '-at_install', 'portal', 'souscriptions_regularisation')
class PortalRegularisationTestCase(SouscriptionsTestMixin, HttpCase):
    """Factures de régularisation ÉMISES au portail (tranche 8 du PRD #231,
    #240, ADR 0030 conséquences) : même règle que l'historique des périodes
    — une facture de régul en brouillon ne fuite jamais côté usager·ère, et
    seul·e le·la souscripteur·rice concerné·e y accède."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()

        cls.portal_user = cls.env['res.users'].create(
            {
                'name': 'Portal Regul User',
                'login': 'portal_regul',
                'email': 'portal_regul@test.com',
                'group_ids': [(6, 0, [cls.env.ref('base.group_portal').id])],
            }
        )
        cls.partner_test.user_ids = [(6, 0, [cls.portal_user.id])]

        cls.regularisation_emise = cls._creer_regularisation_facturee(
            cls.souscription_base, date(2024, 1, 1), date(2024, 2, 1), poster=True
        )
        cls.regularisation_brouillon = cls._creer_regularisation_facturee(
            cls.souscription_base, date(2024, 3, 1), date(2024, 4, 1), poster=False
        )

    @classmethod
    def _creer_regularisation_facturee(cls, souscription, date_debut, date_fin, ecart_kwh=50.0, poster=True):
        """Régularisation minimale, sa ligne directement construite (grille ×
        cadran) — même isolation que test_regularisation_facture.py : la
        sélection des candidats (`_recalculer`, appel electricore) n'est pas
        nécessaire pour tester la surface portail."""
        regularisation = cls.env['souscription.regularisation'].create(
            {'souscription_id': souscription.id, 'date_debut': date_debut, 'date_fin': date_fin}
        )
        cls.env['souscription.regularisation.ligne'].create(
            {
                'regularisation_id': regularisation.id,
                'grille_id': cls.grille_prix.id,
                'cadran': 'base',
                'ecart_kwh': ecart_kwh,
                'prix_kwh': 0.15,
                'detail': f'{date_debut.strftime("%B %Y")} : {ecart_kwh:.2f} kWh',
            }
        )
        facture = regularisation._creer_facture()
        if poster:
            facture.action_post()
        return regularisation

    def _detail_url(self, souscription=None):
        souscription = souscription or self.souscription_base
        return f'/my/souscription/{souscription.id}'

    def test_facture_regularisation_emise_visible_et_telechargeable(self):
        """Une facture de régularisation émise est listée dans une section
        dédiée et son lien pointe vers la route de téléchargement portail
        native, qui répond effectivement."""
        self.authenticate(self.portal_user.login, self.portal_user.login)
        response = self.url_open(self._detail_url())
        self.assertEqual(response.status_code, 200)

        self.assertIn('Factures de régularisation', response.text)
        facture = self.regularisation_emise.facture_id
        self.assertEqual(facture.state, 'posted')
        self.assertIn(facture.name, response.text)
        self.assertIn(f'/my/invoices/{facture.id}', response.text)

        # Sans suivre les redirections : un 200 après redirect vers /my serait
        # un refus déguisé, pas un téléchargement.
        telechargement = self.url_open(f'/my/invoices/{facture.id}', allow_redirects=False)
        self.assertEqual(telechargement.status_code, 200)

    def test_facture_regularisation_brouillon_invisible(self):
        """Une régularisation dont la facture reste en brouillon ne fuite pas
        (ni son lien, ni sa référence) — même garde que les périodes."""
        facture_brouillon = self.regularisation_brouillon.facture_id
        self.assertEqual(facture_brouillon.state, 'draft')

        self.authenticate(self.portal_user.login, self.portal_user.login)
        response = self.url_open(self._detail_url())
        self.assertEqual(response.status_code, 200)

        self.assertNotIn(f'/my/invoices/{facture_brouillon.id}', response.text)

    def test_acces_facture_regularisation_reserve_au_souscripteur(self):
        """Un·e autre usager·ère ne voit ni la page de la souscription
        d'autrui, ni ne peut télécharger sa facture de régularisation."""
        other_partner = self.env['res.partner'].create({'name': 'Autre Régul', 'email': 'autre_regul@test.com'})
        other_user = self.env['res.users'].create(
            {
                'name': 'Other Regul Portal User',
                'login': 'other_regul_portal',
                'email': 'other_regul_portal@test.com',
                'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
            }
        )
        other_partner.user_ids = [(6, 0, [other_user.id])]

        self.authenticate(other_user.login, other_user.login)
        response = self.url_open(self._detail_url())
        self.assertEqual(response.status_code, 403)

        # La route portail native ne renvoie pas 403 : sur AccessError elle
        # REDIRIGE vers /my. C'est la redirection qui est le refus — un 200
        # direct serait la fuite.
        facture = self.regularisation_emise.facture_id
        telechargement = self.url_open(f'/my/invoices/{facture.id}', allow_redirects=False)
        self.assertIn(telechargement.status_code, (302, 303))
        self.assertNotIn('/my/invoices', telechargement.headers.get('Location', ''))
