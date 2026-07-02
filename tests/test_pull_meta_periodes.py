"""
Tests du pull des méta-périodes (#77, ADR 0011/0019/0020).

Deux tranches :
- `_amorcer_depuis_meta` / `_releve_vals_depuis_objet` : mapping pur
  `PeriodeMeta`/`ObjetReleve` → `create()`, testé avec des stubs duck-typés
  (aucune dépendance à `electricore_client`, cf. la garde d'import du wizard).
- Le wizard « Récupérer les périodes du mois » : create-missing-only,
  skip-and-report, erreurs typées mappées — client mocké.

Fixtures RSC/PDL : identifiants factices (jamais des vrais échantillons).
"""

from datetime import date
from types import SimpleNamespace

from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


def _objet_releve(**kwargs):
    """Stub duck-typé d'`ObjetReleve` (contrat v3) : mêmes attributs, valeurs
    par défaut à None pour les champs optionnels du contrat."""
    base = dict(
        releve_id='ELC-RELEVE-001',
        date_releve='2024-01-31',
        nature_index='reel',
        origine_releve='flux_R151',
        evenement=None,
        index_base_kwh=None,
        index_hp_kwh=None,
        index_hc_kwh=None,
        index_hph_kwh=None,
        index_hch_kwh=None,
        index_hpb_kwh=None,
        index_hcb_kwh=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _periode_meta(**kwargs):
    """Stub duck-typé de `PeriodeMeta` (contrat v3) : mêmes attributs que le
    modèle pydantic réel, mêmes noms — le mapping ne fait aucune traduction."""
    base = dict(
        ref_situation_contractuelle='RSC-00000000000001',
        pdl='14000000000001',
        mois_annee='2024-01',
        debut='2024-01-01',
        fin='2024-02-01',
        nb_jours=31,
        puissance_moyenne_kva=6.0,
        formule_tarifaire_acheminement='CU4',
        energie_base_kwh=280.0,
        energie_hp_kwh=None,
        energie_hc_kwh=None,
        turpe_fixe_eur=8.5,
        turpe_variable_eur=4.2,
        cta_eur=1.1,
        taux_accise_eur_mwh=21.0,
        has_changement=False,
        qualite='reelle',
        statut_communication='communicante',
        releves_utilises=[],
        source_hash='hash-abc123',
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


@tagged('souscriptions', 'souscriptions_pull_meta', 'post_install', '-at_install')
class TestAmorcerDepuisMeta(SouscriptionsTestCase):
    """Mapping pur `PeriodeMeta` → `create()` (aucun client requis)."""

    def test_mappe_les_champs_du_contrat_sans_traduction(self):
        meta = _periode_meta()
        periode = self.env['souscription.periode']._amorcer_depuis_meta(self.souscription_base, meta)

        self.assertEqual(periode.date_debut, date(2024, 1, 1))
        self.assertEqual(periode.date_fin, date(2024, 2, 1))
        self.assertEqual(periode.puissance_moyenne_kva, 6.0)
        self.assertEqual(periode.energie_base_kwh, 280.0)
        self.assertEqual(periode.turpe_fixe, 8.5)
        self.assertEqual(periode.turpe_variable, 4.2)
        self.assertEqual(periode.cta_eur, 1.1)
        self.assertEqual(periode.taux_accise_eur_mwh, 21.0)
        self.assertEqual(periode.qualite, 'reelle')
        self.assertEqual(periode.statut_communication, 'communicante')
        self.assertEqual(periode.source_hash, 'hash-abc123')
        self.assertFalse(periode.has_changement)

    def test_qualite_incalculable_creee_quand_meme(self):
        """Une période incalculable est créée, énergies nulles (brouillon
        facturable, CONTEXT.md / ADR 0020 §4)."""
        meta = _periode_meta(
            qualite='incalculable',
            statut_communication=None,
            energie_base_kwh=None,
            energie_hp_kwh=None,
            energie_hc_kwh=None,
        )
        periode = self.env['souscription.periode']._amorcer_depuis_meta(self.souscription_base, meta)

        self.assertEqual(periode.qualite, 'incalculable')
        self.assertEqual(periode.energie_base_kwh, 0.0)

    def test_releves_utilises_deviennent_des_enfants_avec_provenance(self):
        """`releves_utilises` -> relevés enfants, provenance conservée
        (releve_externe_id, origine) — ADR 0020 §6."""
        meta = _periode_meta(
            releves_utilises=[
                _objet_releve(
                    releve_id='ELC-RELEVE-100',
                    date_releve='2024-01-01',
                    nature_index='reel',
                    origine_releve='flux_R151',
                    index_base_kwh=1000,
                ),
                _objet_releve(
                    releve_id='ELC-RELEVE-101',
                    date_releve='2024-01-31',
                    nature_index='estime',
                    origine_releve='estimation_electricore',
                    index_base_kwh=1280,
                ),
            ]
        )
        periode = self.env['souscription.periode']._amorcer_depuis_meta(self.souscription_base, meta)

        self.assertEqual(len(periode.releve_ids), 2)
        premier, second = periode.releve_ids.sorted('date')
        self.assertEqual(premier.releve_externe_id, 'ELC-RELEVE-100')
        self.assertEqual(premier.origine, 'flux_R151')
        self.assertEqual(premier.nature, 'reel')
        self.assertEqual(premier.index_base, 1000.0)
        self.assertEqual(second.nature, 'estime')

    def test_nature_corrige_devient_reel(self):
        """`nature_index='corrige'` (réel révisé) atterrit en `reel` (ADR 0020 §6)."""
        meta = _periode_meta(
            releves_utilises=[_objet_releve(nature_index='corrige')],
        )
        periode = self.env['souscription.periode']._amorcer_depuis_meta(self.souscription_base, meta)
        self.assertEqual(periode.releve_ids.nature, 'reel')

    def test_evenement_prime_sur_origine_releve_pour_lorigine(self):
        """Un relevé d'événement C15 documente son origine par `evenement`
        (précision), sinon on retombe sur `origine_releve` (ADR 0020 §6)."""
        meta = _periode_meta(
            releves_utilises=[
                _objet_releve(origine_releve='flux_C15', evenement='CHGCPT'),
            ],
        )
        periode = self.env['souscription.periode']._amorcer_depuis_meta(self.souscription_base, meta)
        self.assertEqual(periode.releve_ids.origine, 'CHGCPT')

    def test_create_missing_only_ne_reecrit_jamais_lexistant(self):
        """Un `(souscription, mois)` déjà amorcé n'est jamais réécrit
        automatiquement (ADR 0011) : garde vérifiée au niveau wizard, pas ici —
        ce test verrouille la clé (contrainte unique mensuelle, ADR 0020 §2)."""
        self.env['souscription.periode']._amorcer_depuis_meta(self.souscription_base, _periode_meta())
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.env['souscription.periode']._amorcer_depuis_meta(self.souscription_base, _periode_meta())
