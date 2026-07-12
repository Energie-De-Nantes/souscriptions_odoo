from datetime import date

from odoo.tests.common import TransactionCase, tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'post_install', '-at_install')
class TestSouscription(TransactionCase):
    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create(
            {
                'name': 'Test Client',
                'is_company': False,
            }
        )

    def test_souscription_creation(self):
        """Test création basique d'une souscription"""
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL123456',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'date_debut': date(2024, 1, 1),
            }
        )

        self.assertEqual(souscription.partner_id, self.partner)
        self.assertEqual(souscription.puissance_souscrite, '6')
        self.assertEqual(souscription.type_tarif, 'base')
        self.assertTrue(souscription.name != 'Nouveau')  # Séquence générée

    def test_souscription_hphc(self):
        """Test création souscription HP/HC"""
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL789',
                'puissance_souscrite': '9',
                'type_tarif': 'hphc',
                'provision_mensuelle_kwh': 500.0,
            }
        )

        self.assertEqual(souscription.type_tarif, 'hphc')
        self.assertEqual(souscription.provision_mensuelle_kwh, 500.0)

    def test_provisions_cadrans_repartition_70_30(self):
        """_provisions_cadrans() répartit la provision mensuelle 70% HP / 30% HC
        quand hp/hc ne sont pas renseignées explicitement (issue #73)."""
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL_REPARTITION',
                'puissance_souscrite': '9',
                'type_tarif': 'hphc',
                'provision_mensuelle_kwh': 500.0,
            }
        )

        provisions = souscription._provisions_cadrans()

        self.assertEqual(provisions['hp'], 350.0)
        self.assertEqual(provisions['hc'], 150.0)
        self.assertEqual(provisions['base'], 500.0)

    def test_provisions_cadrans_explicites_priment(self):
        """_provisions_cadrans() renvoie les provisions HP/HC explicites telles
        quelles (cas raccordement) sans passer par la répartition 70/30, même si
        provision_mensuelle_kwh vaut 0 (issue #73)."""
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL_EXPLICITE',
                'puissance_souscrite': '9',
                'type_tarif': 'hphc',
                'provision_hp_kwh': 200.0,
                'provision_hc_kwh': 120.0,
            }
        )

        provisions = souscription._provisions_cadrans()

        self.assertEqual(provisions['hp'], 200.0)
        self.assertEqual(provisions['hc'], 120.0)

    def test_coefficient_pro(self):
        """Test majoration PRO"""
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL456',
                'puissance_souscrite': '12',
                'type_tarif': 'base',
                'coeff_pro': 15.5,
            }
        )

        self.assertEqual(souscription.coeff_pro, 15.5)

    def test_tarif_solidaire(self):
        """Test tarif solidaire"""
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL999',
                'puissance_souscrite': '3',
                'type_tarif': 'base',
                'tarif_solidaire': True,
            }
        )

        self.assertTrue(souscription.tarif_solidaire)

    def test_rsc_et_id_affaire_saisissables_a_la_main(self):
        """`ref_situation_contractuelle` (clé d'articulation) et `id_affaire`
        (amorce de réconciliation, ADR 0010) sont saisissables à la main tant
        que le raccordement ne les peuple pas (#76, ADR 0020 §3)."""
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL_RSC',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'ref_situation_contractuelle': 'RSC0001234',
                'id_affaire': 'AFF-56789',
            }
        )

        self.assertEqual(souscription.ref_situation_contractuelle, 'RSC0001234')
        self.assertEqual(souscription.id_affaire, 'AFF-56789')

    def test_adresse_pdl_creation(self):
        """Champ d'atterrissage migration (#106, ADR 0023) : l'adresse du PDL
        se crée et se lit telle quelle, distincte de l'adresse du·de la
        souscripteur·rice (`partner_id`)."""
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner.id,
                'pdl': 'PDL_ADRESSE',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'adresse_pdl': '12 rue de la Paix\n44000 Nantes',
            }
        )

        self.assertEqual(souscription.adresse_pdl, '12 rue de la Paix\n44000 Nantes')

    def test_adresse_pdl_visible_sur_le_formulaire(self):
        """L'adresse du PDL est exposée au formulaire Souscription (#106)."""
        view = self.env['souscription.souscription'].get_view(view_type='form')
        self.assertIn('adresse_pdl', view['arch'])

    def test_mode_paiement_selection_verrouillee(self):
        """Le chèque énergie est un tiers-payeur, pas un mode de règlement
        (#184, CONTEXT.md « Mode de paiement ») : il ne doit plus apparaître
        parmi les valeurs possibles."""
        valeurs = [key for key, _ in self.env['souscription.souscription']._fields['mode_paiement'].selection]
        self.assertEqual(
            valeurs,
            ['prelevement', 'monnaie_locale', 'especes', 'virement', 'cheque'],
        )
        self.assertNotIn('cheque_energie', valeurs)


@tagged('souscriptions', 'post_install', '-at_install')
class TestNaissanceDepuisDemande(SouscriptionsTestCase):
    """Couture #218 (PRD #215 tranche 3/3, CONTEXT.md « Raccordement ») :
    `naitre_depuis_demande(demande)` porte tous les invariants de naissance
    — mapping complet, naissance lissée, octroi du portail, journalisation
    des actes. La demande n'orchestre plus que l'intake mince (partner créé
    à part) : ces tests appellent la couture directement, sans passer par le
    kanban, pour l'isoler de l'orchestration d'acceptation."""

    def _demande(self, **kwargs):
        defaults = {
            'pdl': 'PDL_NAISSANCE',
            'date_debut_souhaitee': date(2026, 1, 1),
            'puissance_souscrite': '9',
            'type_tarif': 'base',
            'provision_mensuelle_kwh': 300.0,
            'contact_nom': 'Titulaire',
            'contact_email': 'naissance@example.com',
            'contact_street': 'Test Street',
            'contact_zip': '44000',
            'contact_city': 'Nantes',
            'mode_paiement': 'virement',
        }
        defaults.update(kwargs)
        demande = self.env['raccordement.demande'].create(defaults)
        # Intake déjà fait (hors scope de la naissance) : le partner est
        # assigné à la main, comme le ferait `_create_odoo_entries` avant
        # d'appeler `naitre_depuis_demande`.
        demande.partner_id = self.partner_test
        return demande

    def test_mapping_complet_tarif_base(self):
        demande = self._demande(coeff_pro=7.5, situation_entree='mes', id_affaire='AFF-218-001')
        souscription = self.env['souscription.souscription'].naitre_depuis_demande(demande)

        self.assertEqual(souscription.partner_id, self.partner_test)
        self.assertEqual(souscription.pdl, 'PDL_NAISSANCE')
        self.assertEqual(souscription.date_debut, date(2026, 1, 1))
        self.assertEqual(souscription.puissance_souscrite, '9')
        self.assertEqual(souscription.type_tarif, 'base')
        self.assertEqual(souscription.provision_mensuelle_kwh, 300.0)
        self.assertEqual(souscription.coeff_pro, 7.5)
        self.assertEqual(souscription.id_affaire, 'AFF-218-001')
        self.assertEqual(souscription.id_affaire_date_saisie, demande.id_affaire_date_saisie)
        self.assertTrue(souscription.lisse, 'La naissance active toujours le lissage')

    def test_mapping_provisions_hphc(self):
        demande = self._demande(
            type_tarif='hphc', provision_hp_kwh=150.0, provision_hc_kwh=90.0, provision_mensuelle_kwh=0.0
        )
        souscription = self.env['souscription.souscription'].naitre_depuis_demande(demande)

        self.assertEqual(souscription.type_tarif, 'hphc')
        self.assertEqual(souscription.provision_hp_kwh, 150.0)
        self.assertEqual(souscription.provision_hc_kwh, 90.0)

    def test_cotitulaires_recopies(self):
        cotitulaire = self.env['res.partner'].create({'name': 'Cotitulaire Naissance'})
        demande = self._demande(cotitulaires=[(6, 0, cotitulaire.ids)])

        souscription = self.env['souscription.souscription'].naitre_depuis_demande(demande)

        self.assertEqual(souscription.cotitulaires, cotitulaire)

    def test_octroi_acces_portail(self):
        demande = self._demande()

        self.env['souscription.souscription'].naitre_depuis_demande(demande)

        self.assertTrue(self.partner_test.user_ids, 'Un utilisateur portail doit être créé')
        self.assertTrue(self.partner_test.user_ids._is_portal())

    def test_actes_adhesion_journalises_a_la_date_de_signature(self):
        signature = date(2026, 2, 1)
        demande = self._demande(date_validation=signature, renonce_retractation=True)

        souscription = self.env['souscription.souscription'].naitre_depuis_demande(demande)

        acceptation = souscription._dernier_acte('acceptation_cgv')
        renonciation = souscription._dernier_acte('renonciation_retractation')
        self.assertTrue(acceptation, "L'acceptation CGV devrait être journalisée")
        self.assertTrue(renonciation, 'La renonciation devrait être journalisée')
        self.assertEqual(acceptation.date_consentement.date(), signature)
        self.assertEqual(renonciation.date_consentement.date(), signature)

    def test_aucun_acte_sans_date_de_signature(self):
        """Pas de date de signature = pas d'acte (ADR 0027), même si la
        renonciation est cochée."""
        demande = self._demande(renonce_retractation=True)

        souscription = self.env['souscription.souscription'].naitre_depuis_demande(demande)

        self.assertFalse(souscription._dernier_acte('acceptation_cgv'))
        self.assertFalse(souscription._dernier_acte('renonciation_retractation'))

    def test_consentements_rgpd_journalises_par_finalite(self):
        demande = self._demande(consent_conso_quotidienne=True, consent_courbe_charge=False)

        souscription = self.env['souscription.souscription'].naitre_depuis_demande(demande)

        self.assertEqual(souscription.etat_consentement('conso_quotidienne'), 'donne')
        self.assertFalse(souscription.etat_consentement('courbe_charge'))

    def test_create_reste_vierge_dinvariants_de_naissance(self):
        """`create()` (migration/imports, #218) ne déclenche ni octroi
        portail ni journalisation des actes — chemin inchangé, invariants de
        naissance hors de portée."""
        partner = self.env['res.partner'].create({'name': 'Import Test', 'email': 'import-218@example.com'})

        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': partner.id,
                'pdl': 'PDL_IMPORT_218',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
            }
        )

        self.assertFalse(partner.user_ids, 'create() ne doit pas octroyer le portail')
        self.assertFalse(souscription.consentement_ids, 'create() ne doit journaliser aucun acte')


@tagged('souscriptions', 'post_install', '-at_install')
class TestSouscriptionFactureCount(SouscriptionsTestCase):
    """Bouton stat « N Factures » de la button box (#199) : facture_count
    compte les factures d'énergie liées via les Périodes (ADR 0004) et
    action_voir_factures ouvre la liste filtrée sur ces factures."""

    def test_facture_count_zero_sans_facture(self):
        self.assertEqual(self.souscription_base.facture_count, 0)

    def test_facture_count_compte_les_factures_liees(self):
        periode, facture = self.create_test_invoice(self.souscription_base)
        self.assertEqual(self.souscription_base.facture_count, 1)
        self.assertEqual(self.souscription_base.facture_ids, facture)

    def test_action_voir_factures_ouvre_la_liste_filtree(self):
        periode, facture = self.create_test_invoice(self.souscription_base)
        action = self.souscription_base.action_voir_factures()
        self.assertEqual(action['res_model'], 'account.move')
        self.assertEqual(action['domain'], [('id', 'in', facture.ids)])
