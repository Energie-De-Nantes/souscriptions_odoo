"""Tests #187 — pont raccordement -> mandat SEPA actif à l'acceptation
(PRD #183, CONTEXT.md « Mandat de prélèvement (SEPA) »).

Le modèle de mandat (`sdd.mandate`) vit dans le module Enterprise « Direct
Debit », absent en Community/CI (décision PRD #183 : pas de dépendance
manifeste à un module privé). La seule couture testable ici sans lui est la
méthode pure de construction des valeurs (`_mandat_sepa_vals`) et la
résolution du journal SDD (`_resoudre_journal_sdd`, lecture seule sur
`account.journal`/`account.payment.method`, tous deux Community) ; le garde
runtime (`_creer_mandat_sepa`) se teste côté no-op — la création réelle d'un
`sdd.mandate` ne peut être exercée qu'en instance Enterprise, hors de portée
de cette suite.
"""

from datetime import date, timedelta
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from .common import SouscriptionsTestMixin

IBAN_VALIDE = 'FR1420041010050500013M02606'


def _demande_defaults(email):
    return {
        'pdl': 'TEST_MANDAT_' + email,
        'date_debut_souhaitee': date.today() + timedelta(days=30),
        'puissance_souscrite': '6',
        'contact_nom': 'Test',
        'contact_email': email,
        'contact_street': 'Test Street',
        'contact_zip': '12345',
        'contact_city': 'Test City',
        'mode_paiement': 'prelevement',
        'bank_iban': IBAN_VALIDE,
    }


@tagged('souscriptions', 'souscriptions_raccordement', 'post_install', '-at_install')
class TestMandatSepaValsPur(SouscriptionsTestMixin, TransactionCase):
    """`_mandat_sepa_vals` : construction pure, sans accès au registre ni à
    la base au-delà des champs de `self` — la seam Community/CI de #187."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        cls.partner = cls.env['res.partner'].create({'name': 'Mandat Vals Partner'})
        cls.partner_bank = cls.env['res.partner.bank'].create({'partner_id': cls.partner.id, 'acc_number': IBAN_VALIDE})
        cls.journal = cls.env['account.journal'].create(
            {'name': 'Journal Test Mandat', 'code': 'MNDT', 'type': 'bank', 'company_id': cls.env.company.id}
        )

    def create_demande(self, **kwargs):
        defaults = _demande_defaults('mandat-vals@example.com')
        defaults.update(kwargs)
        return self.env['raccordement.demande'].create(defaults)

    def test_rum_saisi_repris_tel_quel(self):
        demande = self.create_demande(sepa_mandate_ref='SEPA-TEST-001')
        vals = demande._mandat_sepa_vals(self.partner, self.partner_bank, self.journal)
        self.assertEqual(vals['name'], 'SEPA-TEST-001')

    def test_rum_absent_laisse_le_defaut_de_l_outillage_generer(self):
        demande = self.create_demande(sepa_mandate_ref=False)
        vals = demande._mandat_sepa_vals(self.partner, self.partner_bank, self.journal)
        self.assertNotIn('name', vals)

    def test_date_debut_reprend_la_date_de_signature(self):
        demande = self.create_demande(sepa_mandate_date=date(2026, 3, 15))
        vals = demande._mandat_sepa_vals(self.partner, self.partner_bank, self.journal)
        self.assertEqual(vals['start_date'], date(2026, 3, 15))

    def test_date_debut_par_defaut_aujourd_hui_si_signature_absente(self):
        demande = self.create_demande(sepa_mandate_date=False)
        vals = demande._mandat_sepa_vals(self.partner, self.partner_bank, self.journal)
        self.assertEqual(vals['start_date'], date.today())

    def test_compte_bancaire_partenaire_et_journal_repris_tels_quels(self):
        demande = self.create_demande()
        vals = demande._mandat_sepa_vals(self.partner, self.partner_bank, self.journal)
        self.assertEqual(vals['partner_id'], self.partner.id)
        self.assertEqual(vals['partner_bank_id'], self.partner_bank.id)
        self.assertEqual(vals['payment_journal_id'], self.journal.id)

    def test_actif_d_emblee_schema_core(self):
        demande = self.create_demande()
        vals = demande._mandat_sepa_vals(self.partner, self.partner_bank, self.journal)
        self.assertEqual(vals['state'], 'active')
        self.assertEqual(vals['scheme'], 'CORE')


@tagged('souscriptions', 'souscriptions_raccordement', 'post_install', '-at_install')
class TestResoudreJournalSdd(SouscriptionsTestMixin, TransactionCase):
    """`_resoudre_journal_sdd` : résolution dynamique (jamais configurée en
    dur), erreur explicite si introuvable ou ambigu (#187)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()

    def create_demande(self, **kwargs):
        defaults = _demande_defaults('journal-sdd@example.com')
        defaults.update(kwargs)
        return self.env['raccordement.demande'].create(defaults)

    def _donner_methode_sdd(self, journal):
        # (code, payment_type) est unique : une seule méthode sdd, partagée
        method = self.env['account.payment.method'].search(
            [('code', '=', 'sdd'), ('payment_type', '=', 'inbound')], limit=1
        ) or self.env['account.payment.method'].create({'name': 'SDD Test', 'code': 'sdd', 'payment_type': 'inbound'})
        self.env['account.payment.method.line'].create(
            {'name': 'SDD', 'payment_method_id': method.id, 'journal_id': journal.id}
        )

    def test_leve_si_aucun_journal_sdd(self):
        demande = self.create_demande()
        with self.assertRaises(UserError) as cm:
            demande._resoudre_journal_sdd()
        self.assertIn('SDD', str(cm.exception))

    def test_resout_le_journal_unique(self):
        journal = self.env['account.journal'].create(
            {'name': 'Journal SDD Unique', 'code': 'SDDU', 'type': 'bank', 'company_id': self.env.company.id}
        )
        self._donner_methode_sdd(journal)
        demande = self.create_demande()
        self.assertEqual(demande._resoudre_journal_sdd(), journal)

    def test_leve_si_journaux_ambigus(self):
        journal_a = self.env['account.journal'].create(
            {'name': 'Journal SDD A', 'code': 'SDDA', 'type': 'bank', 'company_id': self.env.company.id}
        )
        journal_b = self.env['account.journal'].create(
            {'name': 'Journal SDD B', 'code': 'SDDB', 'type': 'bank', 'company_id': self.env.company.id}
        )
        self._donner_methode_sdd(journal_a)
        self._donner_methode_sdd(journal_b)
        demande = self.create_demande()
        with self.assertRaises(UserError) as cm:
            demande._resoudre_journal_sdd()
        self.assertIn('Plusieurs', str(cm.exception))


@tagged('souscriptions', 'souscriptions_raccordement', 'post_install', '-at_install')
class TestCreerMandatSepaGuard(SouscriptionsTestMixin, TransactionCase):
    """Garde runtime (#187) : `sdd.mandate` absent du registre en
    Community/CI -> no-op silencieux, acceptation inchangée ; un autre mode
    de paiement ne crée jamais de mandat."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        cls.stage_final = cls.env.ref('souscriptions_odoo.stage_accepte_iban_verifie')

    def create_demande(self, email, **kwargs):
        defaults = _demande_defaults(email)
        defaults.update(kwargs)
        return self.env['raccordement.demande'].create(defaults)

    def test_registre_sans_sdd_mandate_en_community(self):
        """Confirme l'hypothèse sur laquelle repose tout ce fichier : cette
        suite tourne en Community/CI, sans le modèle Enterprise."""
        self.assertNotIn('sdd.mandate', self.env)

    def test_creer_mandat_sepa_noop_sans_outillage(self):
        demande = self.create_demande('guard-noop@example.com')
        partner = self.env['res.partner'].create({'name': 'Mandat Guard Partner'})
        partner_bank = self.env['res.partner.bank'].create({'partner_id': partner.id, 'acc_number': demande.bank_iban})
        # La résolution de journal planterait sans `sdd.mandate` (aucun
        # journal SDD configuré) : si elle était appelée malgré le garde,
        # cette assertion le détecterait immédiatement.
        with patch.object(
            type(demande), '_resoudre_journal_sdd', side_effect=AssertionError('ne doit pas être appelé')
        ):
            demande._creer_mandat_sepa(partner, partner_bank)  # ne doit pas lever
        self.assertFalse(demande.sepa_mandate_ref)

    def test_acceptation_prelevement_sans_outillage_comportement_inchange(self):
        """AC #187 : acceptation en prélèvement sans l'outillage -> aucun
        crash, souscription et compte bancaire créés comme avant #187."""
        demande = self.create_demande('guard-accept@example.com')
        demande.stage_id = self.stage_final
        self.assertTrue(demande.souscription_id)
        self.assertTrue(demande.partner_bank_id)

    def test_acceptation_autre_mode_aucun_mandat_cree(self):
        """AC #187 : hors prélèvement, `_creer_mandat_sepa` n'est même pas
        invoquée."""
        demande = self.create_demande('guard-virement@example.com', mode_paiement='virement', bank_iban=False)
        with patch.object(type(demande), '_creer_mandat_sepa') as mock_creer:
            demande.stage_id = self.stage_final
        mock_creer.assert_not_called()
        self.assertTrue(demande.souscription_id)
