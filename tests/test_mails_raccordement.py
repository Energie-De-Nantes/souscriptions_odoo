"""Tests #102 — mails de rassurage F120/F130 à l'entrée des branches ⏳
(ADR 0022 §6) : un template par branche, envoyé à l'entrée effective
(initiale ou re-routée), jamais à un autre changement d'étape.

Pas de nouvelle couture : assertion directe sur les `mail.mail` générés
(`send_mail(force_send=False)` crée l'enregistrement sans tenter d'envoi
SMTP), comme le reste de la suite raccordement.
"""

from datetime import date, timedelta

from odoo.tests.common import TransactionCase, tagged

from .common import SouscriptionsTestMixin


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
        self.assertNotEqual(self.template_f120.subject, self.template_f130.subject)

    def test_reroute_f120_vers_f130_envoie_mail_de_la_branche_darrivee(self):
        demande = self.create_demande('mail-reroute@example.com', situation_entree='mes', id_affaire='AFF-MAIL-003')
        self.assertEqual(demande.stage_id, self.stage_f120_mes)
        self.assertEqual(len(self._mails(demande)), 1)

        demande.situation_entree = 'cfne'

        self.assertEqual(demande.stage_id, self.stage_f130_cfne)
        mails = self._mails(demande)
        self.assertEqual(len(mails), 2, 'Le re-routage doit envoyer un second mail (celui de la nouvelle branche)')
        self.assertEqual(mails.sorted('id')[-1].subject, self.template_f130.subject)

    def test_autre_changement_detape_nenvoie_pas_de_rassurage(self):
        """Un changement d'étape hors branche ⏳ (drag manuel classique)
        n'envoie aucun rassurage."""
        demande = self.create_demande('mail-aucun@example.com', pro=True, siret='12345678901234')
        self.assertEqual(demande.stage_id, self.stage_pro_a_valider)

        demande.stage_id = self.stage_nouveau

        self.assertFalse(self._mails(demande))
