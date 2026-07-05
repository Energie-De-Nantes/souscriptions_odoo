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

import unittest
from contextlib import contextmanager
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from odoo.addons.souscriptions_odoo.models.core import electricore_client_fabrique as fabrique_module
from odoo.addons.souscriptions_odoo.models.wizard import souscription_pull_meta_periodes_wizard as wizard_module
from odoo.exceptions import UserError
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


# === Wizard « Récupérer les périodes du mois » : client mocké ===
#
# Exceptions factices mirant exactement les noms/sémantiques d'
# electricore_client.exceptions (le paquet réel peut être absent du sandbox
# d'exécution des tests ; le module wizard ne les utilise que par leur nom
# importé, patché ci-dessous).


class _FakeIngestionEnCours(Exception):
    pass


class _FakePreconditionNonRemplie(Exception):
    pass


class _FakeContractVersionError(Exception):
    pass


@contextmanager
def _stream(metas):
    """Mime `JsonlStream` : context manager itérable, cf.
    electricore_client.streaming.JsonlStream."""
    yield iter(metas)


def _fake_client(metas=(), *, leve=None):
    """Client factice : `.meta_periodes(mois=, rsc=)` renvoie un flux
    (context manager) qui itère `metas`, ou lève `leve` à l'ouverture."""
    client = MagicMock()
    if leve is not None:
        client.meta_periodes.side_effect = leve
    else:
        client.meta_periodes.return_value = _stream(metas)
    return client


@tagged('souscriptions', 'souscriptions_pull_meta', 'post_install', '-at_install')
class TestWizardPullMetaPeriodes(SouscriptionsTestCase):
    def setUp(self):
        super().setUp()
        patcher_exc = patch.multiple(
            wizard_module,
            IngestionEnCours=_FakeIngestionEnCours,
            PreconditionNonRemplie=_FakePreconditionNonRemplie,
            ContractVersionError=_FakeContractVersionError,
        )
        patcher_exc.start()
        self.addCleanup(patcher_exc.stop)

    def _wizard(self, mois=date(2024, 1, 1)):
        return self.env['souscription.pull.meta.periodes.wizard'].create({'mois': mois})

    def _lancer_avec_client(self, client, mois=date(2024, 1, 1)):
        """Lance le wizard avec un client factice fourni directement par la
        fabrique (ADR 0024) : la garde paquet/config de la fabrique est
        testée une fois dans test_electricore_client_fabrique.py, pas ici."""
        wizard = self._wizard(mois)
        with patch.object(fabrique_module.SouscriptionElectricoreClient, 'client', return_value=client):
            wizard.action_lancer()
        return wizard

    def test_cree_les_periodes_manquantes_pour_les_souscriptions_a_rsc(self):
        """AC2 : le wizard crée les périodes manquantes du mois pour les
        souscriptions à RSC."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        meta = _periode_meta(
            ref_situation_contractuelle='RSC-00000000000001',
            debut='2024-01-01',
            fin='2024-02-01',
        )
        client = _fake_client([meta])

        wizard = self._lancer_avec_client(client)

        periode = self.env['souscription.periode'].search(
            [('souscription_id', '=', self.souscription_base.id), ('mois', '=', date(2024, 1, 1))]
        )
        self.assertEqual(len(periode), 1)
        self.assertIn('Créées : 1', wizard.resultat)
        self.assertEqual(wizard.state, 'done')
        client.meta_periodes.assert_called_once_with(mois='2024-01-01', rsc=['RSC-00000000000001'])

    def test_ne_reecrit_jamais_une_periode_existante(self):
        """AC2 : create-missing-only — une période déjà amorcée n'est jamais
        réécrite, même avec des valeurs différentes dans le payload."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        existante = self.create_test_periode(
            self.souscription_base, date_debut=date(2024, 1, 1), date_fin=date(2024, 2, 1)
        )
        existante.cta_eur = 1.23

        meta = _periode_meta(
            ref_situation_contractuelle='RSC-00000000000001',
            debut='2024-01-01',
            fin='2024-02-01',
            cta_eur=999.0,
        )
        wizard = self._lancer_avec_client(_fake_client([meta]))

        self.assertEqual(existante.cta_eur, 1.23)
        self.assertIn('Déjà existantes : 1', wizard.resultat)
        self.assertIn('Créées : 0', wizard.resultat)

    def test_resume_les_souscriptions_sans_rsc(self):
        """AC3 : résumé skip-and-report — souscriptions sans RSC comptées à part."""
        self.assertFalse(self.souscription_hphc.ref_situation_contractuelle)
        wizard = self._lancer_avec_client(_fake_client([]))
        self.assertIn('Sans RSC (ignorées) :', wizard.resultat)
        self.assertNotIn('Sans RSC (ignorées) : 0', wizard.resultat)

    def test_souscription_en_instance_nee_du_raccordement_hors_pull(self):
        """#101 AC5 : une Souscription *en instance* (née à l'acceptation,
        sans RSC) reste hors du pull — comportement du pull clé RSC/mois
        (AC3 ci-dessus), asserté ici sur une Souscription née du
        Raccordement plutôt que sur une fixture directe."""
        demande = self.env['raccordement.demande'].create(
            {
                'pdl': 'PDL_RACC_HORS_PULL',
                'date_debut_souhaitee': date.today() + timedelta(days=30),
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'provision_mensuelle_kwh': 250.0,
                'contact_nom': 'Test',
                'contact_email': 'racc-hors-pull@example.com',
                'contact_street': 'Test Street',
                'contact_zip': '12345',
                'contact_city': 'Test City',
                'mode_paiement': 'virement',
            }
        )
        demande.stage_id = self.env.ref('souscriptions_odoo.stage_accepte_iban_verifie')
        souscription = demande.souscription_id
        self.assertTrue(souscription, "La Souscription devrait naître à l'acceptation")
        self.assertEqual(souscription.etat, 'en_instance')

        wizard = self._lancer_avec_client(_fake_client([]))

        self.assertIn(souscription.name, wizard.resultat)
        periode = self.env['souscription.periode'].search([('souscription_id', '=', souscription.id)])
        self.assertFalse(periode, 'Aucune période ne doit être amorcée pour une Souscription en instance')

    def test_releves_crees_avec_identifiant_externe_et_origine(self):
        """AC4 : relevés créés avec identifiant externe + origine."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        meta = _periode_meta(
            ref_situation_contractuelle='RSC-00000000000001',
            debut='2024-01-01',
            fin='2024-02-01',
            releves_utilises=[_objet_releve(releve_id='ELC-999', origine_releve='flux_R151')],
        )
        self._lancer_avec_client(_fake_client([meta]))

        releve = self.env['souscription.releve'].search([('releve_externe_id', '=', 'ELC-999')])
        self.assertEqual(len(releve), 1)
        self.assertEqual(releve.origine, 'flux_R151')

    def test_erreur_par_periode_ne_bloque_pas_le_lot(self):
        """Skip-and-report par élément : une erreur d'amorçage sur une RSC
        n'empêche pas les autres d'être traitées, et apparaît dans le résumé."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        meta_invalide = _periode_meta(
            ref_situation_contractuelle='RSC-00000000000001',
            debut=None,  # déclenche une erreur de mapping (Date invalide)
            fin='2024-02-01',
        )
        wizard = self._lancer_avec_client(_fake_client([meta_invalide]))
        self.assertIn('Erreurs : 1', wizard.resultat)

    def test_ingestion_en_cours_mappee_en_userror_reessayable(self):
        """AC5 : IngestionEnCours -> message « réessayer plus tard »."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        client = _fake_client(leve=_FakeIngestionEnCours('verrou'))
        with self.assertRaises(UserError) as cm:
            self._lancer_avec_client(client)
        self.assertIn('plus tard', str(cm.exception))

    def test_precondition_non_remplie_mappee_en_userror_actionnable(self):
        """AC5 : PreconditionNonRemplie -> message actionnable du serveur conservé."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        client = _fake_client(leve=_FakePreconditionNonRemplie('réconciliez les RSC avant de facturer'))
        with self.assertRaises(UserError) as cm:
            self._lancer_avec_client(client)
        self.assertIn('réconciliez les RSC', str(cm.exception))

    def test_contract_version_error_mappee_en_erreur_dure(self):
        """AC5 : ContractVersionError -> erreur dure (UserError, pas de retry implicite)."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        client = _fake_client(leve=_FakeContractVersionError('serveur v2 < attendu v3'))
        with self.assertRaises(UserError) as cm:
            self._lancer_avec_client(client)
        self.assertIn('v2', str(cm.exception))

    def test_aucune_souscription_a_rsc_naboutit_pas_a_un_appel_de_flux(self):
        """Aucune RSC facturable -> aucun flux n'est ouvert (pas de round-trip
        réseau inutile), même si le client est acquis en tête (fast-fail,
        ADR 0024 §5 : la construction elle-même n'ouvre aucune socket)."""
        client = _fake_client([])
        wizard = self._lancer_avec_client(client)
        client.meta_periodes.assert_not_called()
        self.assertIn('Sans RSC', wizard.resultat)


@unittest.skipIf(
    not fabrique_module.ELECTRICORE_CLIENT_DISPONIBLE,
    'electricore_client non installé : test exercé uniquement là où le paquet réel est présent (CI Docker).',
)
@tagged('souscriptions', 'souscriptions_pull_meta', 'post_install', '-at_install')
class TestAmorcerDepuisMetaAvecPaquetReel(SouscriptionsTestCase):
    """`_amorcer_depuis_meta` face aux vrais modèles pydantic `PeriodeMeta`/
    `ObjetReleve` (contrat v3) — pas seulement les stubs duck-typés ci-dessus.
    Vérifie que le mapping accepte le type réel que le client renverra en
    production, sans écart de champ (ADR 0019 : contrat single-source)."""

    def test_mappe_un_vrai_periode_meta_pydantic(self):
        from electricore_client import ObjetReleve, PeriodeMeta

        meta = PeriodeMeta(
            ref_situation_contractuelle='RSC-00000000000001',
            pdl='14000000000001',
            mois_annee='2024-01',
            debut='2024-01-01',
            fin='2024-02-01',
            nb_jours=31,
            puissance_moyenne_kva=6.0,
            energie_base_kwh=280.0,
            turpe_fixe_eur=8.5,
            turpe_variable_eur=4.2,
            cta_eur=1.1,
            taux_accise_eur_mwh=21.0,
            has_changement=False,
            qualite='reelle',
            statut_communication='communicante',
            releves_utilises=[
                ObjetReleve(
                    releve_id='ELC-RELEVE-100',
                    date_releve='2024-01-01',
                    nature_index='reel',
                    origine_releve='flux_R151',
                    index_base_kwh=1000,
                )
            ],
            source_hash='hash-abc123',
        )

        periode = self.env['souscription.periode']._amorcer_depuis_meta(self.souscription_base, meta)

        self.assertEqual(periode.date_debut, date(2024, 1, 1))
        self.assertEqual(periode.energie_base_kwh, 280.0)
        self.assertEqual(periode.qualite, 'reelle')
        self.assertEqual(len(periode.releve_ids), 1)
        self.assertEqual(periode.releve_ids.releve_externe_id, 'ELC-RELEVE-100')
        self.assertEqual(periode.releve_ids.index_base, 1000.0)
