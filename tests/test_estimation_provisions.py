"""Tests #121 — estimation des provisions à l'étape « Calcul de mensualités »
(GET /provision/estimation).

Couture de test : on patche `_appeler_estimation`, la méthode transport de
`raccordement.demande`, avec des réponses en boîte. Le client lui-même est
fourni directement par la fabrique patchée (`souscription.electricore.client`,
ADR 0024) — sa garde paquet/config est testée une fois dans
test_electricore_client_fabrique.py, pas ici. Aucun HTTP réel.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import requests
from odoo.addons.souscriptions_odoo.models.core import electricore_client_fabrique as fabrique_module
from odoo.addons.souscriptions_odoo.models.raccordement import raccordement_demande as demande_module
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


def _estimation(**kwargs):
    """Stub de l'enveloppe `estimation` (dict plat, contrat electricore)."""
    base = dict(
        energie_base_kwh=3360.0,
        energie_hp_kwh=None,
        energie_hc_kwh=None,
        energie_base_mensuel_kwh=280.0,
        energie_hp_mensuel_kwh=None,
        energie_hc_mensuel_kwh=None,
        profondeur_cadran='base',
        couverture_mois=12.0,
        couverture_debut='2023-01-01',
        couverture_fin='2024-01-01',
        couverture_suffisante=True,
        qualite='bonne',
        presence_regularisation=False,
        signal_alertable=False,
    )
    base.update(kwargs)
    return base


def _reponse(trouve=True, estimation=None, contract_version=1):
    """Stub de l'enveloppe JSON de `GET /provision/estimation`."""
    return {
        'contract_version': contract_version,
        'pdl': 'PDL_ESTIMATION_TEST',
        'as_of': '2024-01-01',
        'trouve': trouve,
        'estimation': estimation,
    }


def _http_error_503(detail=None):
    """Stub de `requests.exceptions.HTTPError` (503), avec ou sans `detail`
    JSON — mime `response.raise_for_status()`."""
    response = MagicMock()
    response.status_code = 503
    response.json.return_value = {'detail': detail} if detail else {}
    return requests.exceptions.HTTPError(response=response)


@tagged('souscriptions', 'souscriptions_estimation_provisions', 'post_install', '-at_install')
class TestEstimationProvisions(SouscriptionsTestCase):
    def setUp(self):
        super().setUp()
        # Le client est fourni directement par la fabrique patchée : la garde
        # paquet/config (ADR 0024) est hors sujet ici (cf.
        # test_electricore_client_fabrique.py).
        self.fake_client = MagicMock(url='https://electricore.example.test', api_key='fake-api-key')
        patcher = patch.object(fabrique_module.SouscriptionElectricoreClient, 'client', return_value=self.fake_client)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _patch_appeler_estimation(self, return_value=None, side_effect=None):
        return patch.object(
            demande_module.RaccordementDemande,
            '_appeler_estimation',
            return_value=return_value,
            side_effect=side_effect,
        )

    def _creer_demande(self, **kwargs):
        vals = dict(
            pdl='PDL_ESTIMATION_TEST',
            date_debut_souhaitee=date.today() + timedelta(days=30),
            puissance_souscrite='6',
            type_tarif='base',
            contact_nom='Test',
            contact_email='estimation-provisions@example.com',
            contact_street='Test Street',
            contact_zip='12345',
            contact_city='Test City',
            mode_paiement='virement',
        )
        vals.update(kwargs)
        return self.env['raccordement.demande'].create(vals)

    def _demande_calcul_mensualites(self, **kwargs):
        demande = self._creer_demande(**kwargs)
        demande.stage_id = self.env.ref('souscriptions_odoo.stage_calcul_mensualites')
        return demande

    # --- Pré-remplissage selon le tarif ---

    def test_base_pre_rempli(self):
        demande = self._demande_calcul_mensualites(type_tarif='base')
        avant = len(demande.message_ids)
        estimation = _estimation(energie_base_mensuel_kwh=312.5)

        with self._patch_appeler_estimation(return_value=_reponse(estimation=estimation)):
            demande.action_estimer_provisions()

        self.assertEqual(demande.provision_mensuelle_kwh, 312.5)
        # Un seul post par clic (pas de spam).
        self.assertEqual(len(demande.message_ids) - avant, 1)

    def test_hphc_pre_rempli(self):
        demande = self._demande_calcul_mensualites(type_tarif='hphc')
        estimation = _estimation(
            profondeur_cadran='hp_hc',
            energie_hp_mensuel_kwh=210.0,
            energie_hc_mensuel_kwh=95.0,
        )

        with self._patch_appeler_estimation(return_value=_reponse(estimation=estimation)):
            demande.action_estimer_provisions()

        self.assertEqual(demande.provision_hp_kwh, 210.0)
        self.assertEqual(demande.provision_hc_kwh, 95.0)

    def test_hphc_profondeur_insuffisante_ne_remplit_rien(self):
        """profondeur_cadran == 'base' (ou champs hp/hc null) sur un tarif
        HP/HC -> repli manuel, aucun champ pré-rempli."""
        demande = self._demande_calcul_mensualites(type_tarif='hphc')
        avant_hp, avant_hc = demande.provision_hp_kwh, demande.provision_hc_kwh
        avant_msgs = len(demande.message_ids)
        estimation = _estimation(profondeur_cadran='base', energie_hp_mensuel_kwh=None, energie_hc_mensuel_kwh=None)

        with self._patch_appeler_estimation(return_value=_reponse(estimation=estimation)):
            demande.action_estimer_provisions()

        self.assertEqual(demande.provision_hp_kwh, avant_hp)
        self.assertEqual(demande.provision_hc_kwh, avant_hc)
        self.assertEqual(len(demande.message_ids) - avant_msgs, 1)
        self.assertIn('profondeur', demande.message_ids[0].body.lower())

    # --- trouve=False / 503 : jamais bloquant ---

    def test_trouve_false_necrit_rien(self):
        demande = self._demande_calcul_mensualites(type_tarif='base')
        avant = demande.provision_mensuelle_kwh
        avant_msgs = len(demande.message_ids)

        with self._patch_appeler_estimation(return_value=_reponse(trouve=False, estimation=None)):
            demande.action_estimer_provisions()  # ne doit pas lever

        self.assertEqual(demande.provision_mensuelle_kwh, avant)
        self.assertEqual(len(demande.message_ids) - avant_msgs, 1)

    def test_503_ne_leve_pas_userror(self):
        """503 = état opérationnel attendu (flux R67 pas encore matérialisé) :
        chatter + notification non bloquante, jamais une UserError."""
        demande = self._demande_calcul_mensualites(type_tarif='base')
        avant_msgs = len(demande.message_ids)

        with self._patch_appeler_estimation(side_effect=_http_error_503('flux R67 non matérialisé')):
            resultat = demande.action_estimer_provisions()  # ne doit pas lever

        self.assertEqual(resultat['type'], 'ir.actions.client')
        self.assertEqual(resultat['tag'], 'display_notification')
        self.assertEqual(resultat['params']['type'], 'warning')
        self.assertFalse(resultat['params']['sticky'])
        self.assertEqual(len(demande.message_ids) - avant_msgs, 1)

    # --- Éditabilité + recopie vers la Souscription ---

    def test_valeurs_restent_editables_apres_estimation(self):
        demande = self._demande_calcul_mensualites(type_tarif='base')
        with self._patch_appeler_estimation(return_value=_reponse(estimation=_estimation())):
            demande.action_estimer_provisions()

        demande.write({'provision_mensuelle_kwh': 999.0})
        self.assertEqual(demande.provision_mensuelle_kwh, 999.0)

    def test_recopie_vers_souscription_inchangee(self):
        """La recopie des provisions vers la Souscription à la validation
        (`souscription.souscription.naitre_depuis_demande`, #218) reste
        inchangée par #121."""
        demande = self._creer_demande(type_tarif='hphc', provision_hp_kwh=210.0, provision_hc_kwh=95.0)
        demande.stage_id = self.env.ref('souscriptions_odoo.stage_accepte_iban_verifie')

        souscription = demande.souscription_id
        self.assertTrue(souscription, "La Souscription devrait naître à l'acceptation")
        self.assertEqual(souscription.provision_hp_kwh, 210.0)
        self.assertEqual(souscription.provision_hc_kwh, 95.0)
