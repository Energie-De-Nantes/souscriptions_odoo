"""
Tests du bouton « Chronologie » (#200, ADR 0024).

Deux tranches, même découpage que `test_pull_meta_periodes.py` :
- `_vals_depuis_ligne` : mapping pur des 3 types de ligne (`LigneEvenement` /
  `LigneReleve` / `LignePeriodeEnergie`) vers les `vals` de `create()`, testé
  avec des stubs duck-typés (aucune dépendance à `electricore_client`).
- `action_ouvrir_chronologie` : sans RSC (UserError actionnable), purge entre
  deux clics, erreurs typées mappées — client mocké.

Fixtures RSC/PDL : identifiants factices (jamais des vrais échantillons).
"""

from types import SimpleNamespace

from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


def _ligne_evenement(**kwargs):
    """Stub duck-typé de `LigneEvenement` (contrat v1 chronologie)."""
    base = dict(
        type_ligne='evenement',
        date='2024-01-01',
        pdl='14000000000001',
        ref_situation_contractuelle='RSC-00000000000001',
        source='flux_C15',
        type_fait='MES',
        evenement_declencheur='MES',
        puissance_souscrite_kva=6.0,
        formule_tarifaire_acheminement='CU4',
        niveau_ouverture_services='service_complet',
        impacte_abonnement=True,
        resume_modification='Mise en service',
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _ligne_releve(**kwargs):
    """Stub duck-typé de `LigneReleve` (contrat v1 chronologie)."""
    base = dict(
        type_ligne='releve',
        date='2024-01-31',
        pdl='14000000000001',
        ref_situation_contractuelle='RSC-00000000000001',
        source='flux_R151',
        releve_id='ELC-RELEVE-001',
        nature_index='reel',
        origine_releve='périodique',
        ordre_index=1,
        evenement_declencheur=None,
        index_base_kwh=1000,
        index_hp_kwh=None,
        index_hc_kwh=None,
        index_hph_kwh=None,
        index_hch_kwh=None,
        index_hpb_kwh=None,
        index_hcb_kwh=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _ligne_periode_energie(**kwargs):
    """Stub duck-typé de `LignePeriodeEnergie` (contrat v1 chronologie)."""
    base = dict(
        type_ligne='periode_energie',
        date='2024-01-01',
        pdl='14000000000001',
        ref_situation_contractuelle='RSC-00000000000001',
        debut='2024-01-01',
        fin='2024-02-01',
        nb_jours=31,
        qualite='réelle',
        statut_communication='communicante',
        energie_base_kwh=280.0,
        energie_hp_kwh=None,
        energie_hc_kwh=None,
        energie_hph_kwh=None,
        energie_hch_kwh=None,
        energie_hpb_kwh=None,
        energie_hcb_kwh=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


@tagged('souscriptions', 'souscriptions_chronologie', 'post_install', '-at_install')
class TestValsDepuisLigne(SouscriptionsTestCase):
    """Mapping pur des 3 types de ligne (aucun client requis)."""

    def test_mappe_une_ligne_evenement(self):
        Ligne = self.env['souscription.chronologie.ligne']
        vals = Ligne._vals_depuis_ligne(self.souscription_base, _ligne_evenement())

        self.assertEqual(vals['type_ligne'], 'evenement')
        self.assertEqual(vals['date'], '2024-01-01')
        self.assertEqual(vals['pdl'], '14000000000001')
        self.assertEqual(vals['ref_situation_contractuelle'], 'RSC-00000000000001')
        self.assertEqual(vals['type_fait'], 'MES')
        self.assertEqual(vals['puissance_souscrite_kva'], 6.0)
        self.assertEqual(vals['formule_tarifaire_acheminement'], 'CU4')
        self.assertEqual(vals['niveau_ouverture_services'], 'service_complet')
        self.assertTrue(vals['impacte_abonnement'])
        self.assertEqual(vals['resume_modification'], 'Mise en service')
        # Colonnes des deux autres types absentes du mapping evenement.
        self.assertNotIn('releve_id', vals)
        self.assertNotIn('qualite', vals)

    def test_mappe_une_ligne_releve(self):
        Ligne = self.env['souscription.chronologie.ligne']
        vals = Ligne._vals_depuis_ligne(self.souscription_base, _ligne_releve())

        self.assertEqual(vals['type_ligne'], 'releve')
        self.assertEqual(vals['releve_id'], 'ELC-RELEVE-001')
        self.assertEqual(vals['nature_index'], 'reel')
        self.assertEqual(vals['origine_releve'], 'périodique')
        self.assertEqual(vals['ordre_index'], 1)
        self.assertEqual(vals['index_base_kwh'], 1000)
        self.assertIsNone(vals['index_hp_kwh'])
        # Colonnes des deux autres types absentes du mapping releve.
        self.assertNotIn('type_fait', vals)
        self.assertNotIn('qualite', vals)

    def test_mappe_une_ligne_periode_energie(self):
        Ligne = self.env['souscription.chronologie.ligne']
        vals = Ligne._vals_depuis_ligne(self.souscription_base, _ligne_periode_energie())

        self.assertEqual(vals['type_ligne'], 'periode_energie')
        self.assertEqual(vals['debut'], '2024-01-01')
        self.assertEqual(vals['fin'], '2024-02-01')
        self.assertEqual(vals['nb_jours'], 31)
        self.assertEqual(vals['qualite'], 'réelle')
        self.assertEqual(vals['statut_communication'], 'communicante')
        self.assertEqual(vals['energie_base_kwh'], 280.0)
        # Colonnes des deux autres types absentes du mapping periode_energie.
        self.assertNotIn('type_fait', vals)
        self.assertNotIn('releve_id', vals)
