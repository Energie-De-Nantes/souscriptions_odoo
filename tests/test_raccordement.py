"""
Tests pour le module de gestion des raccordements.
"""

from datetime import date, timedelta

from odoo.tests.common import TransactionCase, tagged

from .common import SouscriptionsTestMixin


@tagged('souscriptions', 'souscriptions_raccordement', 'post_install', '-at_install')
class TestRaccordementBasic(SouscriptionsTestMixin, TransactionCase):
    """Tests basiques du module raccordement"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        cls.setUpRaccordementData()

    @classmethod
    def setUpRaccordementData(cls):
        """Setup des données spécifiques aux tests de raccordement"""
        # Créer les étapes de raccordement
        cls.stage_received = cls.env['raccordement.stage'].create(
            {
                'name': 'Test Reçue',
                'sequence': 10,
                'color': 1,
            }
        )

        cls.stage_validated = cls.env['raccordement.stage'].create(
            {
                'name': 'Test Validée',
                'sequence': 20,
                'color': 2,
            }
        )

        cls.stage_final = cls.env['raccordement.stage'].create(
            {
                'name': 'Test Souscrite',
                'sequence': 60,
                'color': 10,
                'is_close': True,
            }
        )

    def test_models_exist(self):
        """Test que les modèles de raccordement existent"""
        self.assertIn('raccordement.demande', self.env)
        self.assertIn('raccordement.stage', self.env)

    def test_mode_paiement_selection_verrouillee(self):
        """Selection jumelle de celle de la Souscription (#184, CONTEXT.md
        « Mode de paiement ») : le chèque énergie est un tiers-payeur, pas un
        mode de règlement, il ne doit plus apparaître."""
        valeurs = [key for key, _ in self.env['raccordement.demande']._fields['mode_paiement'].selection]
        self.assertEqual(
            valeurs,
            ['prelevement', 'monnaie_locale', 'especes', 'virement', 'cheque'],
        )
        self.assertNotIn('cheque_energie', valeurs)

    def test_sequence_generation(self):
        """Test que la séquence de référence fonctionne"""
        demande = self.env['raccordement.demande'].create(
            {
                'pdl': 'TEST123456789',
                'date_debut_souhaitee': date.today() + timedelta(days=30),
                'puissance_souscrite': '6',
                'contact_nom': 'Test',
                'contact_email': 'test@example.com',
                'contact_street': 'Test Street',
                'contact_zip': '12345',
                'contact_city': 'Test City',
            }
        )

        self.assertNotEqual(demande.name, 'Nouveau')
        self.assertTrue(demande.name.startswith('RACC/'))

    def test_default_stage_assignment(self):
        """Test que l'étape par défaut est assignée"""
        demande = self.env['raccordement.demande'].create(
            {
                'pdl': 'TEST123456789',
                'date_debut_souhaitee': date.today() + timedelta(days=30),
                'puissance_souscrite': '6',
                'contact_nom': 'Test',
                'contact_email': 'test@example.com',
                'contact_street': 'Test Street',
                'contact_zip': '12345',
                'contact_city': 'Test City',
            }
        )

        self.assertTrue(demande.stage_id)


@tagged('souscriptions', 'souscriptions_raccordement', 'post_install', '-at_install')
class TestRaccordementIban(SouscriptionsTestMixin, TransactionCase):
    """Tests de validation IBAN"""

    def create_base_demande(self, **kwargs):
        """Helper pour créer une demande de base"""
        defaults = {
            'pdl': 'TEST123456789',
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'contact_nom': 'Test',
            'contact_email': 'test@example.com',
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
        }
        defaults.update(kwargs)
        return self.env['raccordement.demande'].create(defaults)

    # Tests de couture (#216) : le compute délègue à base_iban.validate_iban
    # (ValidationError -> faux) — on ne re-teste pas l'algorithme ISO 13616
    # d'Odoo core, seulement que le champ « IBAN validé » suit son verdict.
    def test_iban_validation_valide(self):
        """IBAN réellement valide (checksum modulo 97 correcte)."""
        demande = self.create_base_demande(bank_iban='FR1420041010050500013M02606')
        self.assertTrue(demande.iban_valide)

    def test_iban_validation_checksum_invalide(self):
        """Même IBAN, checksum modifiée (07 au lieu de 06) : base_iban le
        rejette au modulo 97."""
        demande = self.create_base_demande(bank_iban='FR1420041010050500013M02607')
        self.assertFalse(demande.iban_valide)

    def test_iban_validation_vide(self):
        """IBAN vide : jamais valide."""
        demande = self.create_base_demande(bank_iban='')
        self.assertFalse(demande.iban_valide)

    def test_pro_field_default_and_tracking(self):
        """Test du champ PRO : valeur par défaut et tracking"""
        # Test valeur par défaut (False)
        demande = self.create_base_demande()
        self.assertFalse(demande.pro)

        # Test modification du champ PRO (avec SIRET, requis par la contrainte)
        demande.write({'pro': True, 'siret': '12345678901234'})
        self.assertTrue(demande.pro)

        # Test création avec PRO=True
        demande_pro = self.create_base_demande(pro=True, siret='12345678901234')
        self.assertTrue(demande_pro.pro)


@tagged('souscriptions', 'souscriptions_raccordement_siret', 'post_install', '-at_install')
class TestRaccordementSiret(SouscriptionsTestMixin, TransactionCase):
    """Tests spécifiques pour la validation SIRET"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()

    def create_base_demande(self, **kwargs):
        """Helper pour créer une demande de base"""
        defaults = {
            'pdl': 'TEST123456789',
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'contact_nom': 'Test',
            'contact_email': 'test@example.com',
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
        }
        defaults.update(kwargs)
        return self.env['raccordement.demande'].create(defaults)

    def test_siret_required_for_pro(self):
        """Test que le SIRET est obligatoire pour les demandes PRO"""
        from odoo.exceptions import ValidationError

        # Test que la création PRO sans SIRET échoue
        with self.assertRaises(ValidationError) as cm:
            self.create_base_demande(pro=True)  # Pas de SIRET

        self.assertIn('SIRET est obligatoire', str(cm.exception))

        # Test que la création PRO avec SIRET fonctionne
        demande = self.create_base_demande(pro=True, siret='12345678901234')
        self.assertTrue(demande.pro)
        self.assertEqual(demande.siret, '12345678901234')

    def test_siret_not_required_for_particulier(self):
        """Test que le SIRET n'est pas obligatoire pour les particuliers"""
        # Test création particulier sans SIRET (doit fonctionner)
        demande = self.create_base_demande(pro=False)
        self.assertFalse(demande.pro)
        self.assertFalse(demande.siret)

        # Test création particulier avec SIRET (doit fonctionner aussi)
        demande_avec_siret = self.create_base_demande(pro=False, siret='12345678901234')
        self.assertFalse(demande_avec_siret.pro)
        self.assertEqual(demande_avec_siret.siret, '12345678901234')

    def test_siret_format_validation(self):
        """Test de validation du format SIRET"""
        from odoo.exceptions import ValidationError

        # Test SIRET valide (14 chiffres)
        demande_valid = self.create_base_demande(pro=True, siret='12345678901234')
        self.assertEqual(demande_valid.siret, '12345678901234')

        # Test SIRET trop court
        with self.assertRaises(ValidationError) as cm:
            self.create_base_demande(pro=True, siret='123456789')
        self.assertIn('14 chiffres', str(cm.exception))

        # Test SIRET trop long
        with self.assertRaises(ValidationError) as cm:
            self.create_base_demande(pro=True, siret='123456789012345')
        self.assertIn('14 chiffres', str(cm.exception))

        # Test SIRET avec lettres
        with self.assertRaises(ValidationError) as cm:
            self.create_base_demande(pro=True, siret='1234567890123A')
        self.assertIn('14 chiffres', str(cm.exception))

        # Test SIRET avec caractères spéciaux
        with self.assertRaises(ValidationError) as cm:
            self.create_base_demande(pro=True, siret='12345-67890-123')
        self.assertIn('14 chiffres', str(cm.exception))

    def test_siret_format_cleaning(self):
        """Test que les espaces sont nettoyés dans la validation SIRET"""
        from odoo.exceptions import ValidationError

        # SIRET avec espaces : accepté car la validation nettoie les
        # caractères non numériques avant de compter les 14 chiffres
        demande = self.create_base_demande(pro=True, siret='123 456 789 012 34')
        self.assertEqual(demande.siret, '123 456 789 012 34')

        # SIRET trop court même après nettoyage : refusé
        with self.assertRaises(ValidationError) as cm:
            self.create_base_demande(pro=True, siret='123 456 789 01')
        self.assertIn('14 chiffres', str(cm.exception))

    def test_siret_change_pro_status(self):
        """Test changement de statut PRO avec SIRET"""
        from odoo.exceptions import ValidationError

        # Créer une demande particulière
        demande = self.create_base_demande(pro=False)

        # Passer en PRO sans SIRET (doit échouer)
        with self.assertRaises(ValidationError) as cm:
            demande.pro = True
        self.assertIn('SIRET est obligatoire', str(cm.exception))

        # Ajouter un SIRET puis passer en PRO (doit fonctionner)
        demande.siret = '12345678901234'
        demande.pro = True
        self.assertTrue(demande.pro)
        self.assertEqual(demande.siret, '12345678901234')


@tagged('souscriptions', 'souscriptions_raccordement', 'post_install', '-at_install')
class TestRaccordementWorkflow(SouscriptionsTestMixin, TransactionCase):
    """Tests du workflow de raccordement"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        cls.setUpRaccordementData()

    @classmethod
    def setUpRaccordementData(cls):
        """Setup des données spécifiques aux tests de raccordement"""
        # Utiliser les vraies étapes du module. La naissance de la
        # Souscription (is_close) vit sur « Accepté et IBAN vérifié » (#101,
        # ADR 0022 §2) ; stage_validated sert d'étape intermédiaire distincte
        # pour le test de non-duplication (bounce non-finale).
        cls.stage_received = cls.env.ref('souscriptions_odoo.stage_nouveau')
        cls.stage_validated = cls.env.ref('souscriptions_odoo.stage_calcul_mensualites')
        cls.stage_final = cls.env.ref('souscriptions_odoo.stage_accepte_iban_verifie')

    def create_complete_demande(self, **kwargs):
        """Helper pour créer une demande complète"""
        defaults = {
            'pdl': 'TEST123456789',
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'type_tarif': 'base',
            'provision_mensuelle_kwh': 250.0,
            'contact_nom': 'User',
            'contact_prenom': 'Test',
            'contact_email': 'test@example.com',
            'contact_telephone': '0123456789',
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
            'mode_paiement': 'prelevement',
            'bank_iban': 'FR1420041010050500013M02606',
            'bank_bic': 'BNPAFRPP',
            'bank_acc_holder_name': 'Test User',
            'sepa_mandate_date': date.today(),
            'sepa_mandate_ref': 'SEPA-TEST-001',
        }
        defaults.update(kwargs)
        return self.env['raccordement.demande'].create(defaults)

    def test_create_odoo_entries_complete(self):
        """Test de création des entrées Odoo avec données complètes (particulier)"""
        # Email sans collision avec le partner fixture du setUp
        # (test@example.com) : on teste ici la création pure d'un contact,
        # la réutilisation d'un partner existant a ses propres tests.
        demande = self.create_complete_demande(contact_email='creation@example.com')

        # Passer à l'étape finale
        demande.stage_id = self.stage_final

        # Vérifier que les entrées ont été créées
        self.assertTrue(demande.partner_id, 'Contact devrait être créé')
        self.assertTrue(demande.partner_bank_id, 'Compte bancaire devrait être créé')
        self.assertTrue(demande.souscription_id, 'Souscription devrait être créée')

        # Vérifier les données du contact (particulier)
        partner = demande.partner_id
        self.assertEqual(partner.name, 'Test User')  # prénom + nom
        self.assertEqual(partner.email, 'creation@example.com')
        self.assertEqual(partner.street, 'Test Street')
        self.assertEqual(partner.city, 'Test City')
        self.assertFalse(partner.is_company)  # C'est un particulier

        # Vérifier les données de la souscription
        souscription = demande.souscription_id
        self.assertEqual(souscription.pdl, 'TEST123456789')
        self.assertEqual(souscription.puissance_souscrite, '6')
        self.assertEqual(souscription.type_tarif, 'base')
        self.assertEqual(souscription.partner_id, partner)

        # Accès portail donné dès l'onboarding : le·la souscripteur·trice a
        # désormais un utilisateur portail actif (invitation envoyée).
        self.assertTrue(partner.user_ids, 'Un utilisateur portail doit être créé')
        self.assertTrue(partner.user_ids._is_portal(), 'Utilisateur créé dans le groupe portail')

    def test_create_odoo_entries_pro(self):
        """Test de création des entrées Odoo pour une demande professionnelle"""
        demande = self.create_complete_demande(
            pro=True,
            contact_nom='SARL Test Énergie',  # Nom de société
            contact_prenom='',  # Pas de prénom pour une société
            siret='12345678901234',  # SIRET valide (14 chiffres)
        )

        # Passer à l'étape finale
        demande.stage_id = self.stage_final

        # Vérifier que les entrées ont été créées
        self.assertTrue(demande.partner_id, 'Contact société devrait être créé')
        self.assertTrue(demande.partner_bank_id, 'Compte bancaire devrait être créé')
        self.assertTrue(demande.souscription_id, 'Souscription devrait être créée')

        # Vérifier les données du contact (société)
        partner = demande.partner_id
        self.assertEqual(partner.name, 'SARL Test Énergie')  # Nom de société uniquement
        self.assertEqual(partner.email, 'test@example.com')
        self.assertEqual(partner.street, 'Test Street')
        self.assertEqual(partner.city, 'Test City')
        self.assertTrue(partner.is_company)  # C'est une société

        # Vérifier SIRET seulement si le champ existe (dépend de l10n_fr)
        if 'siret' in self.env['res.partner']._fields:
            self.assertEqual(partner.siret, '12345678901234')  # SIRET transmis

        # Vérifier les données de la souscription
        souscription = demande.souscription_id
        self.assertEqual(souscription.pdl, 'TEST123456789')
        self.assertEqual(souscription.puissance_souscrite, '6')
        self.assertEqual(souscription.type_tarif, 'base')
        self.assertEqual(souscription.partner_id, partner)

    def test_create_odoo_entries_hphc(self):
        """Test de création avec tarif HP/HC"""
        demande = self.create_complete_demande(
            type_tarif='hphc',
            provision_hp_kwh=150.0,
            provision_hc_kwh=100.0,
            provision_mensuelle_kwh=0.0,  # Pas utilisé en HP/HC
        )

        demande.stage_id = self.stage_final

        souscription = demande.souscription_id
        self.assertEqual(souscription.type_tarif, 'hphc')
        self.assertEqual(souscription.provision_hp_kwh, 150.0)
        self.assertEqual(souscription.provision_hc_kwh, 100.0)

    def test_raccordement_hphc_lisse_facture_energie_non_nulle(self):
        """Régression #73 : une souscription HP/HC lissée née du raccordement
        (provision_hp_kwh/provision_hc_kwh peuplées, provision_mensuelle_kwh à 0)
        produit une Période dont les provisions par cadran sont non nulles, et
        dont la facture porte une quantité d'énergie non nulle — cohérente avec
        la mensualité affichée sur les conditions particulières."""
        demande = self.create_complete_demande(
            type_tarif='hphc',
            provision_hp_kwh=150.0,
            provision_hc_kwh=100.0,
            provision_mensuelle_kwh=0.0,
        )

        demande.stage_id = self.stage_final
        souscription = demande.souscription_id
        self.assertTrue(souscription.lisse, 'Le raccordement active le lissage par défaut')

        # La CP affiche une mensualité non nulle pour cette souscription (grille
        # de test active sur 2024, indépendante de la date de début souhaitée).
        mensualite_cp = souscription._prix_documents(a_date=date(2024, 1, 1))['mensualite']
        self.assertGreater(mensualite_cp, 0.0, 'La CP doit afficher une mensualité non nulle')

        periode = self.env['souscription.periode'].create(
            {
                'souscription_id': souscription.id,
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 1, 31),
                'type_periode': 'mensuelle',
            }
        )

        # La Période doit porter des provisions par cadran non nulles, cohérentes
        # avec ce qui a été saisi au raccordement.
        self.assertEqual(periode.provision_hp_kwh, 150.0)
        self.assertEqual(periode.provision_hc_kwh, 100.0)

        produits = [vals for (_cmd, _id, vals) in periode._composer_lignes(self.grille_prix) if vals.get('product_id')]
        hp = next(d for d in produits if d['name'] == 'Énergie HP')
        hc = next(d for d in produits if d['name'] == 'Énergie HC')
        self.assertEqual(hp['quantity'], 150.0)
        self.assertEqual(hc['quantity'], 100.0)
        self.assertGreater(
            hp['quantity'] + hc['quantity'],
            0.0,
            "La facture doit porter une quantité d'énergie non nulle (provision HP+HC)",
        )

    def test_create_odoo_entries_no_bank_for_other_payment(self):
        """Test de création sans compte bancaire pour autre mode de paiement"""
        demande = self.create_complete_demande(
            mode_paiement='virement',
            bank_iban='',
            bank_bic='',
        )

        demande.stage_id = self.stage_final

        self.assertTrue(demande.partner_id, 'Contact devrait être créé')
        self.assertFalse(demande.partner_bank_id, 'Compte bancaire ne devrait pas être créé')
        self.assertTrue(demande.souscription_id, 'Souscription devrait être créée')

    def test_existing_partner_reused_without_identity_overwrite(self):
        """Un partner existant (même nature pro/particulier) est réutilisé,
        mais ses champs d'identité (nom, adresse) ne sont pas écrasés."""
        # Créer un contact existant avec le même email
        existing_partner = self.env['res.partner'].create(
            {
                'name': 'Ancien Nom',
                'email': 'test@example.com',
                'city': 'Ancienne Ville',
                'is_company': False,
            }
        )

        demande = self.create_complete_demande()
        demande.stage_id = self.stage_final

        # Le contact existant est réutilisé (même ID), mais son identité
        # n'est pas écrasée par les données de la demande.
        self.assertEqual(demande.partner_id.id, existing_partner.id)
        self.assertEqual(existing_partner.name, 'Ancien Nom')
        self.assertEqual(existing_partner.city, 'Ancienne Ville')

        # La réutilisation est tracée au chatter de la demande.
        messages = demande.message_ids.mapped('body')
        self.assertTrue(
            any('Ancien Nom' in body or 'existant' in body for body in messages),
            'La réutilisation du partner existant devrait être tracée au chatter',
        )

    def test_pro_demande_does_not_match_particulier_partner(self):
        """Une demande PRO avec l'email d'un particulier existant crée une
        société, sans modifier le particulier existant."""
        existing_particulier = self.env['res.partner'].create(
            {
                'name': 'Jean Dupont',
                'email': 'test@example.com',
                'city': 'Ancienne Ville',
                'is_company': False,
            }
        )

        demande = self.create_complete_demande(
            pro=True,
            contact_nom='SARL Test Énergie',
            contact_prenom='',
            siret='12345678901234',
        )
        demande.stage_id = self.stage_final

        # Une nouvelle société est créée, distincte du particulier existant.
        self.assertTrue(demande.partner_id)
        self.assertNotEqual(demande.partner_id.id, existing_particulier.id)
        self.assertTrue(demande.partner_id.is_company)
        self.assertEqual(demande.partner_id.name, 'SARL Test Énergie')

        # Le particulier existant reste intact.
        self.assertEqual(existing_particulier.name, 'Jean Dupont')
        self.assertFalse(existing_particulier.is_company)
        self.assertEqual(existing_particulier.city, 'Ancienne Ville')

    def test_particulier_demande_does_not_match_pro_partner(self):
        """Une demande particulier avec l'email d'une société existante crée
        un nouveau contact, sans modifier la société existante."""
        existing_company = self.env['res.partner'].create(
            {
                'name': 'Ancienne SARL',
                'email': 'test@example.com',
                'city': 'Ancienne Ville',
                'is_company': True,
            }
        )

        demande = self.create_complete_demande(pro=False)
        demande.stage_id = self.stage_final

        self.assertTrue(demande.partner_id)
        self.assertNotEqual(demande.partner_id.id, existing_company.id)
        self.assertFalse(demande.partner_id.is_company)

        self.assertEqual(existing_company.name, 'Ancienne SARL')
        self.assertTrue(existing_company.is_company)
        self.assertEqual(existing_company.city, 'Ancienne Ville')

    def test_existing_partner_match_is_case_insensitive_on_email(self):
        """La recherche par email doit ignorer la casse."""
        existing_partner = self.env['res.partner'].create(
            {
                'name': 'Ancien Nom',
                'email': 'Test@Example.com',
                'is_company': False,
            }
        )

        demande = self.create_complete_demande(contact_email='TEST@EXAMPLE.COM')
        demande.stage_id = self.stage_final

        self.assertEqual(demande.partner_id.id, existing_partner.id)
        self.assertEqual(existing_partner.name, 'Ancien Nom')

    def test_archived_partner_not_reused(self):
        """Un partner archivé partageant l'email n'est pas réutilisé : une
        demande crée un nouveau contact plutôt que de toucher un contact
        désactivé."""
        archived_partner = self.env['res.partner'].create(
            {
                'name': 'Ancien Contact Archivé',
                'email': 'test@example.com',
                'is_company': False,
                'active': False,
            }
        )

        demande = self.create_complete_demande()
        demande.stage_id = self.stage_final

        self.assertTrue(demande.partner_id)
        self.assertNotEqual(demande.partner_id.id, archived_partner.id)
        self.assertFalse(archived_partner.active)
        self.assertEqual(archived_partner.name, 'Ancien Contact Archivé')

    def test_stage_change_no_duplicate_creation(self):
        """Test qu'on ne crée pas de doublons en changeant d'étape plusieurs fois"""
        demande = self.create_complete_demande()

        # Premier passage à l'étape finale
        demande.stage_id = self.stage_final

        partner_id = demande.partner_id.id
        souscription_id = demande.souscription_id.id

        # Retour en arrière puis nouveau passage
        demande.stage_id = self.stage_validated
        demande.stage_id = self.stage_final

        # Les IDs devraient être identiques
        self.assertEqual(demande.partner_id.id, partner_id)
        self.assertEqual(demande.souscription_id.id, souscription_id)


@tagged('souscriptions', 'souscriptions_raccordement', 'post_install', '-at_install')
class TestRaccordementKanban(SouscriptionsTestMixin, TransactionCase):
    """Tests de la vue kanban et group_expand"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()

    def test_read_group_stage_ids(self):
        """Test que group_expand retourne toutes les étapes"""
        # Créer quelques étapes de test
        stage1 = self.env['raccordement.stage'].create(
            {
                'name': 'Étape 1',
                'sequence': 10,
            }
        )
        stage2 = self.env['raccordement.stage'].create(
            {
                'name': 'Étape 2',
                'sequence': 20,
            }
        )

        # Tester la méthode group_expand
        demande_model = self.env['raccordement.demande']
        stages = demande_model._read_group_stage_ids(self.env['raccordement.stage'], [])

        # Toutes les étapes devraient être retournées
        self.assertIn(stage1, stages)
        self.assertIn(stage2, stages)

    def test_kanban_view_rendering(self):
        """Test que la vue kanban peut être rendue"""
        # Créer une demande de test
        demande = self.env['raccordement.demande'].create(
            {
                'pdl': 'TEST123456789',
                'date_debut_souhaitee': date.today() + timedelta(days=30),
                'puissance_souscrite': '6',
                'contact_nom': 'Test',
                'contact_email': 'test@example.com',
                'contact_street': 'Test Street',
                'contact_zip': '12345',
                'contact_city': 'Test City',
            }
        )

        # Vérifier que les champs nécessaires pour la vue kanban sont présents
        self.assertTrue(demande.name)
        self.assertTrue(demande.pdl)
        self.assertTrue(demande.contact_nom)
        self.assertTrue(demande.date_debut_souhaitee)


@tagged('souscriptions', 'souscriptions_raccordement', 'post_install', '-at_install')
class TestRaccordementSecurity(SouscriptionsTestMixin, TransactionCase):
    """Tests de sécurité et validation"""

    def test_required_fields_validation(self):
        """Test que les champs requis sont validés"""
        from odoo.tools import mute_logger
        from psycopg2 import IntegrityError

        # PDL manquant -> violation de contrainte NOT NULL attendue.
        # mute_logger + savepoint : on attend cet échec SQL, on évite donc
        # qu'il pollue la sortie avec une ligne ERROR et on garde la
        # transaction utilisable.
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.env['raccordement.demande'].create(
                {
                    'date_debut_souhaitee': date.today() + timedelta(days=30),
                    'puissance_souscrite': '6',
                    'contact_nom': 'Test',
                    'contact_email': 'test@example.com',
                    'contact_street': 'Test Street',
                    'contact_zip': '12345',
                    'contact_city': 'Test City',
                }
            )

    def test_email_validation(self):
        """Test que l'email est requis"""
        from odoo.tools import mute_logger
        from psycopg2 import IntegrityError

        # Email manquant -> violation de contrainte NOT NULL attendue.
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.env['raccordement.demande'].create(
                {
                    'pdl': 'TEST123456789',
                    'date_debut_souhaitee': date.today() + timedelta(days=30),
                    'puissance_souscrite': '6',
                    'contact_nom': 'Test',
                    'contact_street': 'Test Street',
                    'contact_zip': '12345',
                    'contact_city': 'Test City',
                }
            )

    def test_stage_constraint(self):
        """Test les contraintes de changement d'étape"""
        demande = self.env['raccordement.demande'].create(
            {
                'pdl': 'TEST123456789',
                'date_debut_souhaitee': date.today() + timedelta(days=30),
                'puissance_souscrite': '6',
                'contact_nom': 'Test',
                'contact_email': 'test@example.com',
                'contact_street': 'Test Street',
                'contact_zip': '12345',
                'contact_city': 'Test City',
                'mode_paiement': 'prelevement',
                'bank_iban': 'INVALID',  # IBAN invalide
            }
        )

        # Essayer de passer à l'étape IBAN validé avec un IBAN invalide
        self.env.ref('souscriptions_odoo.stage_accepte_iban_verifie')

        # L'onchange devrait générer un warning (pas d'exception)
        # On vérifie juste que l'IBAN est invalide
        self.assertFalse(demande.iban_valide)
