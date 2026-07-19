"""Tests du pull des sorties C15 (#246, ADR 0031 décisions 1-2, tranche 1 du
chantier résiliations #21) : `date_fin` gouvernée par le fait C15, à auteur
unique.

Deux tranches :
- Le service `souscription.pull.meta.periodes.service.pull_sorties` —
  idempotence par comparaison de champ (absente -> écrit + chatter ;
  identique -> noop strict ; différente -> corrige + trace), convention de
  borne (`date_fin = date_sortie - 1 jour`), `CFNS` strictement équivalent à
  `RES`, erreurs typées mappées, skip-and-report, transport nommé
  `_appeler_sorties` (RPC, pas un flux).
- Le bouton autonome `souscription.souscription.action_tirer_sorties_c15` —
  construit le périmètre (non résiliées à RSC), délègue au service, formate
  la notification.

Fixtures RSC/PDL : identifiants factices (jamais des vrais échantillons).
"""

from datetime import date

from odoo.addons.souscriptions_odoo.models.core import souscription_pull_meta_periodes_service as service_module
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase, client_sorties_factice, ligne_sortie, patcher_client_fabrique


@tagged('souscriptions', 'souscriptions_pull_sorties', 'post_install', '-at_install')
class TestPullSortiesService(SouscriptionsTestCase):
    def _pull_sorties(self, client, souscriptions):
        with patcher_client_fabrique(client):
            return self.env['souscription.pull.meta.periodes.service'].pull_sorties(souscriptions)

    def test_sortie_absente_ecrit_date_fin_dernier_jour_servi_et_trace_au_chatter(self):
        """AC1 : une sortie RES au 12/06 -> date_fin = 11/06 (dernier jour
        servi, convention de borne ADR 0031 décision 2), etat = 'en_attente_cloture'
        dérive (compute existant) — la clôture n'est pas soldée (aucune
        Période ne couvre encore `date_fin`), tranche 2 #247 ; chatter posé
        avec le code et la date brute."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        client = client_sorties_factice(
            [ligne_sortie('RSC-00000000000001', date(2024, 6, 12), evenement_declencheur='RES')]
        )

        ecrites, corrigees, inchangees, erreurs = self._pull_sorties(client, self.souscription_base)

        self.assertEqual(self.souscription_base.date_fin, date(2024, 6, 11))
        self.assertEqual(self.souscription_base.etat, 'en_attente_cloture')
        self.assertEqual(len(ecrites), 1)
        self.assertFalse(corrigees)
        self.assertFalse(inchangees)
        self.assertFalse(erreurs)
        messages = self.souscription_base.message_ids.mapped('body')
        self.assertTrue(any('RES' in m and '2024-06-12' in m for m in messages))
        client.sorties.assert_called_once_with(rsc=['RSC-00000000000001'])

    def test_repull_naboutit_a_aucune_ecriture_ni_nouveau_message(self):
        """AC2 : re-pull -> zéro écriture, noop tracé nulle part (aucun
        nouveau message chatter)."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        client = client_sorties_factice([ligne_sortie('RSC-00000000000001', date(2024, 6, 12))])
        self._pull_sorties(client, self.souscription_base)
        nb_messages_avant = len(self.souscription_base.message_ids)

        ecrites, corrigees, inchangees, erreurs = self._pull_sorties(client, self.souscription_base)

        self.assertEqual(self.souscription_base.date_fin, date(2024, 6, 11))
        self.assertFalse(ecrites)
        self.assertFalse(corrigees)
        self.assertEqual(len(inchangees), 1)
        self.assertFalse(erreurs)
        self.assertEqual(len(self.souscription_base.message_ids), nb_messages_avant)

    def test_sortie_redatee_corrige_et_trace(self):
        """AC3 : une sortie redatée par Enedis corrige `date_fin` et pose une
        nouvelle trace chatter."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        self._pull_sorties(
            client_sorties_factice([ligne_sortie('RSC-00000000000001', date(2024, 6, 12))]), self.souscription_base
        )
        nb_messages_avant = len(self.souscription_base.message_ids)

        client = client_sorties_factice([ligne_sortie('RSC-00000000000001', date(2024, 6, 20))])
        ecrites, corrigees, inchangees, erreurs = self._pull_sorties(client, self.souscription_base)

        self.assertEqual(self.souscription_base.date_fin, date(2024, 6, 19))
        self.assertFalse(ecrites)
        self.assertEqual(len(corrigees), 1)
        self.assertFalse(inchangees)
        self.assertGreater(len(self.souscription_base.message_ids), nb_messages_avant)

    def test_cfns_strictement_equivalent_a_res(self):
        """AC5 : `CFNS` suit exactement le même chemin que `RES` — le code
        n'apparaît qu'au message, jamais de branche comportementale."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        client = client_sorties_factice(
            [ligne_sortie('RSC-00000000000001', date(2024, 6, 12), evenement_declencheur='CFNS')]
        )

        ecrites, corrigees, inchangees, erreurs = self._pull_sorties(client, self.souscription_base)

        self.assertEqual(self.souscription_base.date_fin, date(2024, 6, 11))
        self.assertEqual(len(ecrites), 1)
        messages = self.souscription_base.message_ids.mapped('body')
        self.assertTrue(any('CFNS' in m for m in messages))

    def test_rsc_hors_du_perimetre_ignoree_silencieusement(self):
        """Une ligne dont la RSC ne matche aucune souscription du lot demandé
        est ignorée (électricore peut renvoyer un sous-ensemble jamais élargi
        en pratique, mais le service reste défensif)."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        client = client_sorties_factice([ligne_sortie('RSC-INCONNUE', date(2024, 6, 12))])

        ecrites, corrigees, inchangees, erreurs = self._pull_sorties(client, self.souscription_base)

        self.assertFalse(ecrites)
        self.assertFalse(corrigees)
        self.assertFalse(inchangees)
        self.assertFalse(erreurs)

    def test_erreur_par_ligne_ne_bloque_pas_le_lot(self):
        """Skip-and-report par élément (ADR 0011) : une erreur sur une ligne
        n'empêche pas les autres d'être traitées."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        self.souscription_hphc.ref_situation_contractuelle = 'RSC-00000000000002'
        client = client_sorties_factice(
            [
                ligne_sortie('RSC-00000000000001', None),  # date_sortie invalide -> erreur au calcul
                ligne_sortie('RSC-00000000000002', date(2024, 6, 12)),
            ]
        )

        ecrites, corrigees, inchangees, erreurs = self._pull_sorties(
            client, self.souscription_base + self.souscription_hphc
        )

        self.assertEqual(len(erreurs), 1)
        self.assertEqual(len(ecrites), 1)
        self.assertEqual(self.souscription_hphc.date_fin, date(2024, 6, 11))

    def test_erreur_par_souscription_va_au_chatter_de_la_souscription_fautive(self):
        """#341, ADR 0036 décision 8a : même geste que le pull méta-périodes —
        l'erreur skip-and-report va au chatter de la souscription fautive, au
        point d'échec dans le service, chemin manuel comme futur automate."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        client = client_sorties_factice([ligne_sortie('RSC-00000000000001', None)])

        self._pull_sorties(client, self.souscription_base)

        messages = self.souscription_base.message_ids.mapped('body')
        self.assertTrue(any('Pull sorties C15' in m for m in messages), 'erreur tracée au chatter')

    def test_ingestion_en_cours_mappee_en_userror_reessayable(self):
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        client = client_sorties_factice(leve=service_module.IngestionEnCours('verrou'))
        with self.assertRaises(UserError) as cm:
            self._pull_sorties(client, self.souscription_base)
        self.assertIn('plus tard', str(cm.exception))

    def test_precondition_non_remplie_mappee_en_userror_actionnable(self):
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        client = client_sorties_factice(
            leve=service_module.PreconditionNonRemplie('réconciliez les RSC avant de facturer')
        )
        with self.assertRaises(UserError) as cm:
            self._pull_sorties(client, self.souscription_base)
        self.assertIn('réconciliez les RSC', str(cm.exception))

    def test_contract_version_error_mappee_en_erreur_dure(self):
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        client = client_sorties_factice(leve=service_module.ContractVersionError('serveur v2 < attendu v3'))
        with self.assertRaises(UserError) as cm:
            self._pull_sorties(client, self.souscription_base)
        self.assertIn('v2', str(cm.exception))

    def test_aucune_souscription_a_rsc_naboutit_pas_a_un_appel_reseau(self):
        """Fast-fail (ADR 0024 §5) : aucune RSC dans le lot -> aucun appel
        réseau, même si le client est acquis en tête."""
        self.assertFalse(self.souscription_hphc.ref_situation_contractuelle)
        client = client_sorties_factice([])
        ecrites, corrigees, inchangees, erreurs = self._pull_sorties(client, self.souscription_hphc)
        client.sorties.assert_not_called()
        self.assertFalse(ecrites)
        self.assertFalse(corrigees)
        self.assertFalse(inchangees)
        self.assertFalse(erreurs)


@tagged('souscriptions', 'souscriptions_pull_sorties', 'post_install', '-at_install')
class TestActionTirerSortiesC15(SouscriptionsTestCase):
    """Bouton autonome (motif sync F15, `souscription.refacturation.
    synchroniser_depuis_electricore`) : périmètre non résiliées à RSC,
    délégation au service, notification formatée. Le câblage dans l'ordre de
    la campagne relève de la tranche 3 (#21) — hors scope ici."""

    def _lancer(self, client):
        with patcher_client_fabrique(client):
            return self.env['souscription.souscription'].action_tirer_sorties_c15()

    def test_perimetre_exclut_les_souscriptions_sans_rsc(self):
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        self.assertFalse(self.souscription_hphc.ref_situation_contractuelle)
        client = client_sorties_factice([ligne_sortie('RSC-00000000000001', date(2024, 6, 12))])

        self._lancer(client)

        client.sorties.assert_called_once_with(rsc=['RSC-00000000000001'])
        self.assertEqual(self.souscription_base.date_fin, date(2024, 6, 11))

    def test_perimetre_exclut_les_souscriptions_deja_resiliees(self):
        self.souscription_base.write(
            {'ref_situation_contractuelle': 'RSC-00000000000001', 'date_fin': date(2024, 1, 31)}
        )
        # Clôture soldée (non-lissé, écarts nuls par construction, ADR 0031
        # décision 3, #247) : la Période contenant `date_fin` facturée suffit
        # -> `resiliee` direct, hors périmètre du pull (même garde que la RSC
        # déjà résolue).
        self.env['souscription.periode'].create(
            {
                'souscription_id': self.souscription_base.id,
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 2, 1),
                'facture_legacy_ref': 'LEGACY-DEJA-RESILIEE-1',
            }
        )
        self.assertEqual(self.souscription_base.etat, 'resiliee')
        client = client_sorties_factice([])

        self._lancer(client)

        client.sorties.assert_not_called()

    def test_notification_resume_les_compteurs(self):
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        client = client_sorties_factice([ligne_sortie('RSC-00000000000001', date(2024, 6, 12))])

        notification = self._lancer(client)

        self.assertEqual(notification['type'], 'ir.actions.client')
        self.assertIn('1', notification['params']['message'])

    def test_methode_donnees_rend_le_tuple_sans_passer_par_le_toast(self):
        """#341, ADR 0036 décision 13 : `_pull_sorties_c15_donnees` — la
        méthode-données consommée par le bouton — est exercée directement,
        sans passer par le payload `display_notification`. Même gabarit que
        `souscription.pull.meta.periodes.service.pull_sorties`."""
        self.souscription_base.ref_situation_contractuelle = 'RSC-00000000000001'
        client = client_sorties_factice([ligne_sortie('RSC-00000000000001', date(2024, 6, 12))])

        with patcher_client_fabrique(client):
            ecrites, corrigees, inchangees, erreurs = self.env['souscription.souscription']._pull_sorties_c15_donnees()

        self.assertEqual(ecrites, [self.souscription_base.name])
        self.assertFalse(corrigees)
        self.assertFalse(inchangees)
        self.assertFalse(erreurs)
