"""Tests de la migration `19.0.1.14.0` — backfill `provision := energie` sur
les Périodes non lissées déjà facturées (#234, ADR 0030 décision 2 —
Énergie facturée universelle).

Charge le script par chemin (`runpy.run_path`, même idiome que
`test_releve.py::TestMigrationIndexInteger` — le dossier de version n'est pas
un identifiant Python importable) et l'exécute contre le curseur réel de la
transaction de test : le script parle SQL brut, `provision_*` étant verrouillé
dès qu'une Période est facturée (#14) — la voie ORM (`write()`) lèverait une
UserError sur exactement les lignes visées ici.
"""

import os
import runpy
from datetime import date

from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_migration', 'post_install', '-at_install')
class TestMigrationEnergieFacturee(SouscriptionsTestCase):
    @staticmethod
    def _migrer(cr):
        chemin = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'migrations', '19.0.1.14.0', 'post-migrate.py'
        )
        module = runpy.run_path(chemin)
        module['migrate'](cr, None)

    def _periode_facturee(self, souscription, **vals):
        """Crée une Période et son `account.move` (out_invoice) — facturée,
        sans passer par `_creer_facture` (on veut la provision non tamponnée,
        comme l'état pré-#234 que la migration doit réparer)."""
        base = {
            'souscription_id': souscription.id,
            'date_debut': date(2024, 1, 1),
            'date_fin': date(2024, 1, 31),
            'type_periode': 'mensuelle',
        }
        base.update(vals)
        periode = self.env['souscription.periode'].create(base)
        self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': souscription.partner_id.id,
                'invoice_date': periode.date_fin,
                'periode_id': periode.id,
            }
        )
        return periode

    def test_backfill_provision_non_lissee_facturee(self):
        """AC4 : une non-lissée déjà facturée reçoit `provision := energie`
        par cadran ; son écart mesuré − facturé est nul après backfill."""
        periode = self._periode_facturee(self.souscription_base, energie_base_kwh=280.0)
        self.assertFalse(periode.lisse_periode)
        self.assertEqual(periode.provision_base_kwh, 0.0)

        self._migrer(self.env.cr)
        periode.invalidate_recordset()

        self.assertEqual(periode.provision_base_kwh, 280.0)
        self.assertEqual(periode.ecart_base_kwh, 0.0)

    def test_backfill_par_cadran_hp_hc(self):
        """Backfill HP/HC : chaque cadran est tamponné indépendamment."""
        souscription = self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner_test.id,
                'pdl': 'PDL_MIGRATION_HPHC',
                'puissance_souscrite': '9',
                'type_tarif': 'hphc',
                'date_debut': date(2024, 1, 1),
            }
        )
        periode = self._periode_facturee(souscription, energie_hp_kwh=210.0, energie_hc_kwh=95.0)
        self.assertFalse(periode.lisse_periode)

        self._migrer(self.env.cr)
        periode.invalidate_recordset()

        self.assertEqual(periode.provision_hp_kwh, 210.0)
        self.assertEqual(periode.provision_hc_kwh, 95.0)
        self.assertEqual(periode.ecart_hp_kwh, 0.0)
        self.assertEqual(periode.ecart_hc_kwh, 0.0)

    def test_lissee_facturee_non_touchee(self):
        """Une Période lissée facturée n'est pas concernée par le backfill —
        elle garde sa provision contractuelle, même si elle diverge du
        mesuré (l'écart lissé se solde en régularisation, pas par backfill)."""
        periode = self._periode_facturee(
            self.souscription_hphc,
            provision_hp_kwh=150.0,
            provision_hc_kwh=100.0,
            energie_hp_kwh=999.0,
            energie_hc_kwh=999.0,
        )
        self.assertTrue(periode.lisse_periode)

        self._migrer(self.env.cr)
        periode.invalidate_recordset()

        self.assertEqual(periode.provision_hp_kwh, 150.0)
        self.assertEqual(periode.provision_hc_kwh, 100.0)

    def test_non_lissee_non_facturee_non_touchee(self):
        """Une Période non lissée mais pas encore facturée (aucun move) n'est
        pas concernée : elle reste le brouillon de travail éditable normal."""
        periode = self.env['souscription.periode'].create(
            {
                'souscription_id': self.souscription_base.id,
                'date_debut': date(2024, 2, 1),
                'date_fin': date(2024, 2, 29),
                'type_periode': 'mensuelle',
                'energie_base_kwh': 280.0,
            }
        )
        self.assertFalse(periode.facture_id)

        self._migrer(self.env.cr)
        periode.invalidate_recordset()

        self.assertEqual(periode.provision_base_kwh, 0.0)

    def test_idempotent_rejouer_sans_effet(self):
        """Rejouer le script après un premier passage est un no-op."""
        periode = self._periode_facturee(self.souscription_base, energie_base_kwh=280.0)

        self._migrer(self.env.cr)
        periode.invalidate_recordset()
        self.assertEqual(periode.provision_base_kwh, 280.0)

        self._migrer(self.env.cr)  # rejoué : rien à corriger
        periode.invalidate_recordset()
        self.assertEqual(periode.provision_base_kwh, 280.0)
