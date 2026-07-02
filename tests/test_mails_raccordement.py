"""Tests #102 — mails de rassurage F120/F130 à l'entrée des branches ⏳
(ADR 0022 §6) : un template par branche, envoyé à l'entrée effective
(initiale ou re-routée), jamais à un autre changement d'étape.

Pas de nouvelle couture : assertion directe sur les `mail.mail` générés
(`send_mail(force_send=False)` crée l'enregistrement sans tenter d'envoi
SMTP), comme le reste de la suite raccordement.
"""

from datetime import date, timedelta

from odoo.tests.common import TransactionCase, tagged

from .common import SouscriptionsTestMixin, build_grille_lignes


@tagged('souscriptions', 'souscriptions_raccordement_mails', 'post_install', '-at_install')
class TestMailsRassurageRaccordement(SouscriptionsTestMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        cls.stage_nouveau = cls.env.ref('souscriptions_odoo.stage_nouveau')
        cls.stage_pro_a_valider = cls.env.ref('souscriptions_odoo.stage_pro_a_valider')
        cls.stage_f120_mes = cls.env.ref('souscriptions_odoo.stage_f120_mes')
        cls.stage_f130_cfne = cls.env.ref('souscriptions_odoo.stage_f130_cfne')
        cls.template_f120 = cls.env.ref('souscriptions_odoo.mail_template_raccordement_f120')
        cls.template_f130 = cls.env.ref('souscriptions_odoo.mail_template_raccordement_f130')

    def create_demande(self, email, **kwargs):
        defaults = {
            'pdl': 'PDL_MAIL_' + email,
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'type_tarif': 'base',
            'provision_mensuelle_kwh': 250.0,
            'contact_nom': 'Test',
            'contact_email': email,
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
        }
        defaults.update(kwargs)
        return self.env['raccordement.demande'].create(defaults)

    def _mails(self, demande):
        return self.env['mail.mail'].search([('res_id', '=', demande.id), ('model', '=', 'raccordement.demande')])

    def test_entree_f120_envoie_mail_rassurage(self):
        demande = self.create_demande('mail-f120@example.com')
        demande.write({'situation_entree': 'mes', 'id_affaire': 'AFF-MAIL-001'})

        self.assertEqual(demande.stage_id, self.stage_f120_mes)
        mails = self._mails(demande)
        self.assertEqual(len(mails), 1)
        self.assertEqual(mails.subject, self.template_f120.subject)
        self.assertEqual(mails.email_to, demande.contact_email)

    def test_entree_f130_envoie_mail_rassurage_template_distinct(self):
        demande = self.create_demande('mail-f130@example.com')
        demande.write({'situation_entree': 'cfne', 'id_affaire': 'AFF-MAIL-002'})

        self.assertEqual(demande.stage_id, self.stage_f130_cfne)
        mails = self._mails(demande)
        self.assertEqual(len(mails), 1)
        self.assertEqual(mails.subject, self.template_f130.subject)
        self.assertEqual(mails.email_to, demande.contact_email)
        self.assertNotEqual(self.template_f120.subject, self.template_f130.subject)

    def test_reroute_f120_vers_f130_envoie_mail_de_la_branche_darrivee(self):
        demande = self.create_demande('mail-reroute@example.com', situation_entree='mes', id_affaire='AFF-MAIL-003')
        self.assertEqual(demande.stage_id, self.stage_f120_mes)
        self.assertEqual(len(self._mails(demande)), 1)

        demande.situation_entree = 'cfne'

        self.assertEqual(demande.stage_id, self.stage_f130_cfne)
        mails = self._mails(demande)
        self.assertEqual(len(mails), 2, 'Le re-routage doit envoyer un second mail (celui de la nouvelle branche)')
        dernier = mails.sorted('id')[-1]
        self.assertEqual(dernier.subject, self.template_f130.subject)
        self.assertEqual(dernier.email_to, demande.contact_email)

    def test_autre_changement_detape_nenvoie_pas_de_rassurage(self):
        """Un changement d'étape hors branche ⏳ (drag manuel classique)
        n'envoie aucun rassurage."""
        demande = self.create_demande('mail-aucun@example.com', pro=True, siret='12345678901234')
        self.assertEqual(demande.stage_id, self.stage_pro_a_valider)

        demande.stage_id = self.stage_nouveau

        self.assertFalse(self._mails(demande))


@tagged('souscriptions', 'souscriptions_raccordement_mails', 'post_install', '-at_install')
class TestPackBienvenueRaccordement(SouscriptionsTestMixin, TransactionCase):
    """Tests #103 — pack de bienvenue automatique à « Abonnement Validé »
    (ADR 0022 §6) : conditions particulières complètes en pièce jointe
    (report_template_ids, même report que le bouton manuel de la
    Souscription — pas de nouvelle couture), documents d'accueil statiques
    configurables, variante par les faits, pas de doublon."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        cls.stage_accepte_iban_verifie = cls.env.ref('souscriptions_odoo.stage_accepte_iban_verifie')
        cls.stage_abonnement_valide = cls.env.ref('souscriptions_odoo.stage_abonnement_valide')
        cls.template_particulier = cls.env.ref('souscriptions_odoo.mail_template_bienvenue_particulier')
        cls.template_pro = cls.env.ref('souscriptions_odoo.mail_template_bienvenue_pro')
        cls.template_solidaire = cls.env.ref('souscriptions_odoo.mail_template_bienvenue_solidaire')
        # La CP jointe au pack se rend à la date de début de la Souscription
        # (date_debut_souhaitee = aujourd'hui + 30 j) : grille ouverte à
        # partir de 2025 pour couvrir cette date quel que soit le jour du
        # run — la grille 2024 du mixin ne couvre que les fixtures
        # historiques (pas de chevauchement).
        grille_courante = cls.env['grille.prix'].create(
            {
                'name': 'Grille Test courante',
                'date_debut': date(2025, 1, 1),
                'date_fin': False,
                'active': True,
            }
        )
        build_grille_lignes(cls.env, grille_courante, prix_base=0.15, prix_hp=0.18, prix_hc=0.12)

    def create_demande(self, email, **kwargs):
        defaults = {
            'pdl': 'PDL_BIENVENUE_' + email,
            'date_debut_souhaitee': date.today() + timedelta(days=30),
            'puissance_souscrite': '6',
            'type_tarif': 'base',
            'provision_mensuelle_kwh': 250.0,
            'contact_nom': 'Test',
            'contact_email': email,
            'contact_street': 'Test Street',
            'contact_zip': '12345',
            'contact_city': 'Test City',
            'mode_paiement': 'virement',
        }
        defaults.update(kwargs)
        return self.env['raccordement.demande'].create(defaults)

    def _mails(self, souscription):
        return self.env['mail.mail'].search(
            [('res_id', '=', souscription.id), ('model', '=', 'souscription.souscription')]
        )

    def _accepter_et_valider(self, demande):
        """Mène la demande jusqu'à « Abonnement Validé » (naissance à
        l'acceptation, #101, puis clôture du kanban)."""
        demande.stage_id = self.stage_accepte_iban_verifie
        demande.stage_id = self.stage_abonnement_valide
        return demande.souscription_id

    def test_drag_en_abonnement_valide_envoie_pack_bienvenue_avec_cp_en_piece_jointe(self):
        demande = self.create_demande('bienvenue-particulier@example.com')
        souscription = self._accepter_et_valider(demande)

        mails = self._mails(souscription)
        self.assertEqual(len(mails), 1)
        self.assertEqual(mails.subject, self.template_particulier.subject)
        self.assertEqual(mails.recipient_ids, souscription.partner_id, 'Le pack part au contact de la demande')
        self.assertTrue(mails.attachment_ids, 'La CP devrait partir en pièce jointe (report_template_ids)')

    def test_variante_pro(self):
        demande = self.create_demande('bienvenue-pro@example.com', pro=True, siret='12345678901234', coeff_pro=5.0)
        souscription = self._accepter_et_valider(demande)

        mails = self._mails(souscription)
        self.assertEqual(len(mails), 1)
        self.assertIn('professionnel', mails.body_html)

    def test_variante_solidaire(self):
        demande = self.create_demande('bienvenue-solidaire@example.com', tarif_solidaire=True)
        souscription = self._accepter_et_valider(demande)

        mails = self._mails(souscription)
        self.assertEqual(len(mails), 1)
        self.assertIn('tarif solidaire', mails.body_html)

    def test_variante_particulier_par_defaut(self):
        demande = self.create_demande('bienvenue-defaut@example.com')
        souscription = self._accepter_et_valider(demande)

        mails = self._mails(souscription)
        self.assertNotIn('professionnel', mails.body_html)
        self.assertNotIn('tarif solidaire', mails.body_html)

    def test_pas_de_doublon_si_reecriture_sans_changement(self):
        demande = self.create_demande('bienvenue-nodup@example.com')
        souscription = self._accepter_et_valider(demande)
        self.assertEqual(len(self._mails(souscription)), 1)

        # Ré-écriture de la même étape (resync, pas un vrai changement) :
        # aucun second pack.
        demande.stage_id = self.stage_abonnement_valide

        self.assertEqual(len(self._mails(souscription)), 1)

    def test_documents_accueil_statiques_partent_avec_le_mail(self):
        """Les documents d'accueil statiques (attachment_ids du template)
        sont configurables et partent avec le mail."""
        piece_jointe = self.env['ir.attachment'].create(
            {
                'name': "Guide d'accueil EDN.pdf",
                'datas': b'ZmFrZSBwZGYgY29udGVudA==',  # 'fake pdf content' en base64
            }
        )
        self.template_particulier.attachment_ids = [(6, 0, [piece_jointe.id])]
        self.addCleanup(lambda: self.template_particulier.write({'attachment_ids': [(5, 0, 0)]}))

        demande = self.create_demande('bienvenue-doc@example.com')
        souscription = self._accepter_et_valider(demande)

        mails = self._mails(souscription)
        noms = mails.attachment_ids.mapped('name')
        self.assertIn("Guide d'accueil EDN.pdf", noms)
