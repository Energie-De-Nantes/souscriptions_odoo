"""Config settings « Souscriptions » (#291) — amorce.

`res.config.settings` hérité expose `journal_monnaie_locale_id`
(`related='company_id.journal_monnaie_locale_id'`, `readonly=False`, ADR
0033) : seul le round-trip config -> société est testé ici, la mécanique qui
casse si le `related` est mal câblé. Le champ lui-même (domaine, check_company)
est déjà couvert par `test_encaissement_une_clic.py` (#290).
"""

from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_config', 'post_install', '-at_install')
class TestResConfigSettingsJournalMonnaieLocale(SouscriptionsTestCase):
    """AC #291 : éditable/persisté par société via `related`, `readonly=False`."""

    def test_ecriture_via_config_persiste_sur_la_societe(self):
        journal = self.env['account.journal'].create(
            {'name': 'Monnaie locale', 'code': 'MNLO', 'type': 'bank', 'company_id': self.env.company.id}
        )
        config = self.env['res.config.settings'].create({'journal_monnaie_locale_id': journal.id})
        config.execute()
        self.assertEqual(self.env.company.journal_monnaie_locale_id, journal)

    def test_lecture_reprend_la_valeur_de_la_societe(self):
        journal = self.env['account.journal'].create(
            {'name': 'Monnaie locale 2', 'code': 'MNL2', 'type': 'bank', 'company_id': self.env.company.id}
        )
        self.env.company.journal_monnaie_locale_id = journal
        config = self.env['res.config.settings'].create({})
        self.assertEqual(config.journal_monnaie_locale_id, journal)
