"""
Tests des champs d'atterrissage du contrat PeriodeMeta v3 electricore
(#76, ADR 0020 §4/§6/§7).

`qualite`/`statut_communication` (verdicts jumeaux), `has_changement`,
`source_hash`, `cta_eur`, `taux_accise_eur_mwh`, `puissance_moyenne_kva`
atterrissent sur la Période sous le nom du contrat. `releve_externe_id` et
`origine` portent la provenance du justificatif sur le Relevé. Tous figés dès
la facturation (ADR 0007), symétrique du verrou existant (#14).
"""

from datetime import date

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_atterrissage', 'post_install', '-at_install')
class TestPeriodeAtterrissage(SouscriptionsTestCase):
    def _periode(self, souscription, **vals):
        base = {
            'souscription_id': souscription.id,
            'date_debut': date(2024, 1, 1),
            'date_fin': date(2024, 2, 1),
            'type_periode': 'mensuelle',
        }
        base.update(vals)
        return self.env['souscription.periode'].create(base)

    def test_champs_atterrissage_persistes(self):
        """Les champs d'atterrissage v3 se créent et se lisent tels quels."""
        periode = self._periode(
            self.souscription_base,
            qualite='estimée',
            statut_communication='non_communicante',
            has_changement=True,
            source_hash='abc123',
            cta_eur=4.2,
            taux_accise_eur_mwh=21.0,
            puissance_moyenne_kva=5.8,
        )

        self.assertEqual(periode.qualite, 'estimée')
        self.assertEqual(periode.statut_communication, 'non_communicante')
        self.assertTrue(periode.has_changement)
        self.assertEqual(periode.source_hash, 'abc123')
        self.assertEqual(periode.cta_eur, 4.2)
        self.assertEqual(periode.taux_accise_eur_mwh, 21.0)
        self.assertEqual(periode.puissance_moyenne_kva, 5.8)

    def test_periode_incalculable_creee_quand_meme(self):
        """Une période `incalculable` reste créable : le brouillon facturable
        est la règle (CONTEXT.md, ADR 0020 §4)."""
        periode = self._periode(self.souscription_base, qualite='incalculable')
        self.assertEqual(periode.qualite, 'incalculable')

    def test_champs_atterrissage_verrouilles_apres_facturation(self):
        """Dès qu'une facture référence la période, les champs d'atterrissage
        sont figés (extension du verrou #14, ADR 0020 §7)."""
        periode = self._periode(self.souscription_base, provision_base_kwh=100.0, cta_eur=4.2)
        periode._creer_facture()

        with self.assertRaises(UserError):
            periode.write({'cta_eur': 999.0})
        with self.assertRaises(UserError):
            periode.write({'qualite': 'réelle'})
        with self.assertRaises(UserError):
            periode.write({'puissance_moyenne_kva': 12.0})

        self.assertEqual(periode.cta_eur, 4.2)


@tagged('souscriptions', 'souscriptions_atterrissage', 'post_install', '-at_install')
class TestReleveProvenance(SouscriptionsTestCase):
    def test_releve_porte_sa_provenance(self):
        """Le Relevé porte `releve_externe_id` et `origine` — identifiant du
        justificatif côté electricore, support de la dédup au re-pull (#76,
        ADR 0020 §6)."""
        periode = self.create_test_periode(self.souscription_base)
        releve = self.env['souscription.releve'].create(
            {
                'periode_id': periode.id,
                'date': date(2024, 1, 1),
                'nature': 'reel',
                'index_base': 12345.0,
                'releve_externe_id': 'ELC-RELEVE-001',
                'origine': 'C15_releve_meter_reading',
            }
        )

        self.assertEqual(releve.releve_externe_id, 'ELC-RELEVE-001')
        self.assertEqual(releve.origine, 'C15_releve_meter_reading')

    def test_releve_provenance_verrouillee_apres_facturation(self):
        """La provenance suit le verrou existant du Relevé (#56, ADR 0020 §7)."""
        periode = self.create_test_periode(self.souscription_base)
        releve = self.env['souscription.releve'].create(
            {
                'periode_id': periode.id,
                'date': date(2024, 1, 1),
                'index_base': 100.0,
                'releve_externe_id': 'ELC-RELEVE-002',
            }
        )
        periode._creer_facture()

        with self.assertRaises(UserError):
            releve.write({'releve_externe_id': 'AUTRE'})
