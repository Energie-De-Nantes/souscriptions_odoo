"""Tests #217 — service `souscription.sepa.mandat` (PRD #215 tranche 2/3).

Le pont mandat SEPA (#187) quitte la demande de raccordement pour un
`AbstractModel` côté core : `creer(partner_bank, date_signature=None,
rum=None) -> mandat | None`. Le modèle de mandat (`sdd.mandate`) vit dans le
module Enterprise « Direct Debit », absent en Community/CI (décision PRD
#183 : pas de dépendance manifeste à un module privé). La seule couture
testable ici sans lui est la méthode pure de construction des valeurs
(`_mandat_sepa_vals`) et la résolution du journal SDD (`_resoudre_journal_sdd`,
lecture seule sur `account.journal`/`account.payment.method`, tous deux
Community) ; le garde runtime (`creer`) se teste côté no-op — la création
réelle d'un `sdd.mandate` ne peut être exercée qu'en instance Enterprise, hors
de portée de cette suite.

Contrairement à l'ancienne suite (`test_raccordement_mandat_sepa.py`, #187),
aucun test ici ne crée de `raccordement.demande` : le service ne connaît pas
la demande, seulement un `partner_bank`, une date de signature et un RUM.
"""

from datetime import date, timedelta
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from .common import SouscriptionsTestMixin

IBAN_VALIDE = 'FR1420041010050500013M02606'


@tagged('souscriptions', 'souscriptions_raccordement', 'post_install', '-at_install')
class TestMandatSepaValsPur(SouscriptionsTestMixin, TransactionCase):
    """`_mandat_sepa_vals` : construction pure, sans accès au registre ni à
    la base au-delà des recordsets passés — la seam Community/CI de #217."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        cls.partner = cls.env['res.partner'].create({'name': 'Mandat Vals Partner'})
        cls.partner_bank = cls.env['res.partner.bank'].create({'partner_id': cls.partner.id, 'acc_number': IBAN_VALIDE})
        cls.journal = cls.env['account.journal'].create(
            {'name': 'Journal Test Mandat', 'code': 'MNDT', 'type': 'bank', 'company_id': cls.env.company.id}
        )
        cls.service = cls.env['souscription.sepa.mandat']

    def test_rum_saisi_repris_tel_quel(self):
        vals = self.service._mandat_sepa_vals(self.partner_bank, self.journal, rum='SEPA-TEST-001')
        self.assertEqual(vals['name'], 'SEPA-TEST-001')

    def test_rum_absent_laisse_le_defaut_de_l_outillage_generer(self):
        vals = self.service._mandat_sepa_vals(self.partner_bank, self.journal)
        self.assertNotIn('name', vals)

    def test_date_debut_reprend_la_date_de_signature(self):
        vals = self.service._mandat_sepa_vals(self.partner_bank, self.journal, date_signature=date(2026, 3, 15))
        self.assertEqual(vals['start_date'], date(2026, 3, 15))

    def test_date_debut_par_defaut_aujourd_hui_si_signature_absente(self):
        vals = self.service._mandat_sepa_vals(self.partner_bank, self.journal)
        self.assertEqual(vals['start_date'], date.today())

    def test_partenaire_derive_du_compte_bancaire_et_journal_repris_tel_quel(self):
        vals = self.service._mandat_sepa_vals(self.partner_bank, self.journal)
        self.assertEqual(vals['partner_id'], self.partner.id)
        self.assertEqual(vals['partner_bank_id'], self.partner_bank.id)
        self.assertEqual(vals['payment_journal_id'], self.journal.id)

    def test_actif_d_emblee_schema_core(self):
        vals = self.service._mandat_sepa_vals(self.partner_bank, self.journal)
        self.assertEqual(vals['state'], 'active')
        self.assertEqual(vals['sdd_scheme'], 'CORE')


@tagged('souscriptions', 'souscriptions_raccordement', 'post_install', '-at_install')
class TestResoudreJournalSdd(SouscriptionsTestMixin, TransactionCase):
    """`_resoudre_journal_sdd` : résolution dynamique (jamais configurée en
    dur), erreur explicite si introuvable ou ambigu (#187, migré #217)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        cls.service = cls.env['souscription.sepa.mandat']

    def _donner_methode_sdd(self, journal):
        # (code, payment_type) est unique : une seule méthode sdd, partagée
        method = self.env['account.payment.method'].search(
            [('code', '=', 'sdd'), ('payment_type', '=', 'inbound')], limit=1
        ) or self.env['account.payment.method'].create({'name': 'SDD Test', 'code': 'sdd', 'payment_type': 'inbound'})
        self.env['account.payment.method.line'].create(
            {'name': 'SDD', 'payment_method_id': method.id, 'journal_id': journal.id}
        )

    def test_leve_si_aucun_journal_sdd(self):
        with self.assertRaises(UserError) as cm:
            self.service._resoudre_journal_sdd()
        self.assertIn('SDD', str(cm.exception))

    def test_resout_le_journal_unique(self):
        journal = self.env['account.journal'].create(
            {'name': 'Journal SDD Unique', 'code': 'SDDU', 'type': 'bank', 'company_id': self.env.company.id}
        )
        self._donner_methode_sdd(journal)
        self.assertEqual(self.service._resoudre_journal_sdd(), journal)

    def test_leve_si_journaux_ambigus_et_pointeur_absent(self):
        """Ambiguïté (>1 journal sdd) sans pointeur société : lève, ne
        devine jamais (#292)."""
        journal_a = self.env['account.journal'].create(
            {'name': 'Journal SDD A', 'code': 'SDDA', 'type': 'bank', 'company_id': self.env.company.id}
        )
        journal_b = self.env['account.journal'].create(
            {'name': 'Journal SDD B', 'code': 'SDDB', 'type': 'bank', 'company_id': self.env.company.id}
        )
        self._donner_methode_sdd(journal_a)
        self._donner_methode_sdd(journal_b)
        with self.assertRaises(UserError) as cm:
            self.service._resoudre_journal_sdd()
        self.assertIn('Plusieurs', str(cm.exception))

    def test_resout_via_pointeur_societe_si_journaux_ambigus(self):
        """Ambiguïté (>1 journal sdd) avec pointeur société pointant vers
        l'un d'eux : résout ce journal-là, sans lever (#292)."""
        journal_a = self.env['account.journal'].create(
            {'name': 'Journal SDD A', 'code': 'SDDA', 'type': 'bank', 'company_id': self.env.company.id}
        )
        journal_b = self.env['account.journal'].create(
            {'name': 'Journal SDD B', 'code': 'SDDB', 'type': 'bank', 'company_id': self.env.company.id}
        )
        self._donner_methode_sdd(journal_a)
        self._donner_methode_sdd(journal_b)
        self.env.company.journal_prelevement_sdd_id = journal_b
        self.assertEqual(self.service._resoudre_journal_sdd(), journal_b)

    def test_leve_si_pointeur_societe_hors_des_journaux_sdd(self):
        """Le pointeur société pointe vers un journal qui n'expose pas sdd :
        lève plutôt que de retourner le mauvais journal (#292)."""
        journal_a = self.env['account.journal'].create(
            {'name': 'Journal SDD A', 'code': 'SDDA', 'type': 'bank', 'company_id': self.env.company.id}
        )
        journal_b = self.env['account.journal'].create(
            {'name': 'Journal SDD B', 'code': 'SDDB', 'type': 'bank', 'company_id': self.env.company.id}
        )
        autre_journal = self.env['account.journal'].create(
            {'name': 'Journal Sans SDD', 'code': 'NOSDD', 'type': 'bank', 'company_id': self.env.company.id}
        )
        self._donner_methode_sdd(journal_a)
        self._donner_methode_sdd(journal_b)
        self.env.company.journal_prelevement_sdd_id = autre_journal
        with self.assertRaises(UserError) as cm:
            self.service._resoudre_journal_sdd()
        self.assertIn('Plusieurs', str(cm.exception))


@tagged('souscriptions', 'souscriptions_raccordement', 'post_install', '-at_install')
class TestCreerMandatSepaGuard(SouscriptionsTestMixin, TransactionCase):
    """Garde runtime (#187, migrée #217) : `sdd.mandate` absent du registre
    en Community/CI -> `creer()` est un no-op silencieux (`None`), sans même
    tenter la résolution du journal SDD."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()
        cls.service = cls.env['souscription.sepa.mandat']
        cls.partner = cls.env['res.partner'].create({'name': 'Mandat Guard Partner'})
        cls.partner_bank = cls.env['res.partner.bank'].create({'partner_id': cls.partner.id, 'acc_number': IBAN_VALIDE})

    def test_registre_sans_sdd_mandate_en_community(self):
        """Confirme l'hypothèse sur laquelle repose tout ce fichier : cette
        suite tourne en Community/CI, sans le modèle Enterprise."""
        self.assertNotIn('sdd.mandate', self.env)

    def test_creer_noop_sans_outillage(self):
        # La résolution de journal planterait sans `sdd.mandate` (aucun
        # journal SDD configuré) : si elle était appelée malgré le garde,
        # cette assertion le détecterait immédiatement.
        with patch.object(
            type(self.service), '_resoudre_journal_sdd', side_effect=AssertionError('ne doit pas être appelé')
        ):
            resultat = self.service.creer(self.partner_bank)
        self.assertIsNone(resultat)

    def test_creer_noop_ignore_date_signature_et_rum(self):
        """No-op quel que soit ce qui est passé : aucun argument ne
        contourne le garde registre."""
        resultat = self.service.creer(
            self.partner_bank, date_signature=date.today() - timedelta(days=1), rum='SEPA-IGNORE'
        )
        self.assertIsNone(resultat)
