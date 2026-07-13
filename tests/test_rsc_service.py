"""Tests #88 — service transport unique de résolution RSC + bouton
« résoudre la RSC maintenant » (ADR 0021 §3, contrat figé
`docs/contrat-rsc.md`).

Couture de test du module (réutilisée par #89, socle commun #222) : on
patche `_appeler`, la méthode transport du service, avec des réponses en
boîte mirant les quatre motifs du contrat RSC. Rien d'autre n'est mocké :
pas de mock d'`electricore_client` lui-même, pas de HTTP, pas de mock du
temps.
"""

from datetime import date

from odoo.addons.souscriptions_odoo.models.core import electricore_rsc_service as service_module
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase, patcher_transport, resultat_rsc

_SERVICE_MODEL = 'souscription.rsc.service'


def _patch_appeler(return_value=None, side_effect=None):
    return patcher_transport(
        service_module.SouscriptionRscService, '_appeler', return_value=return_value, side_effect=side_effect
    )


@tagged('souscriptions', 'souscriptions_rsc_service', 'post_install', '-at_install')
class TestServiceRscTransport(SouscriptionsTestCase):
    """Le service (`souscription.rsc.service`) isolément : appariement,
    lot vide, version de contrat. La garde d'import/config de la fabrique
    (ADR 0024) est testée une fois dans test_electricore_client_fabrique.py."""

    def test_lot_vide_naboutit_pas_a_un_appel(self):
        with _patch_appeler() as mock_appeler:
            resultat = self.env[_SERVICE_MODEL].resoudre([])
        self.assertEqual(resultat, {})
        mock_appeler.assert_not_called()

    def test_apparie_par_id_affaire_tolerant_au_desordre(self):
        """Le lot est apparié par id_affaire, jamais par position : la
        réponse renvoyée dans le désordre reste correctement appariée."""
        reponse_desordonnee = [
            resultat_rsc('B', rsc='RSC-B'),
            resultat_rsc('A', rsc='RSC-A'),
        ]
        with _patch_appeler(return_value=reponse_desordonnee):
            resultat = self.env[_SERVICE_MODEL].resoudre(['A', 'B'])
        self.assertEqual(resultat['A'].ref_situation_contractuelle, 'RSC-A')
        self.assertEqual(resultat['B'].ref_situation_contractuelle, 'RSC-B')

    def test_quatre_motifs_du_contrat(self):
        """Les quatre motifs du contrat RSC (succès + 3 erreurs) traversent
        le service sans traduction, xor rsc/error."""
        reponse = [
            resultat_rsc('OK', rsc='RSC-001'),
            resultat_rsc('INCONNUE', error='Affaire inconnue : INCONNUE'),
            resultat_rsc(
                'SANS-C15',
                error='Affaire connue (X12) sans situation contractuelle C15 '
                '(précurseur en cours ou affaire non contractuelle).',
            ),
            resultat_rsc(
                'AMBIGUE', error="Résolution ambiguë : 2 situations contractuelles pour l'affaire AMBIGUE (X, Y)."
            ),
        ]
        with _patch_appeler(return_value=reponse):
            resultat = self.env[_SERVICE_MODEL].resoudre(['OK', 'INCONNUE', 'SANS-C15', 'AMBIGUE'])

        self.assertEqual(resultat['OK'].ref_situation_contractuelle, 'RSC-001')
        self.assertIsNone(resultat['OK'].error)
        self.assertTrue(resultat['INCONNUE'].error.startswith('Affaire inconnue'))
        self.assertTrue(resultat['SANS-C15'].error.startswith('Affaire connue'))
        self.assertTrue(resultat['AMBIGUE'].error.startswith('Résolution ambiguë'))

    def test_version_de_contrat_inattendue_signalee_sans_ecriture(self):
        """AC2 : version de contrat inattendue -> signalée (UserError), le
        service n'écrit jamais de donnée (l'exception interrompt l'appel
        avant tout accès au résultat)."""
        with _patch_appeler(side_effect=service_module.ContractVersionError('serveur v2 < attendu v3')):
            with self.assertRaises(UserError) as cm:
                self.env[_SERVICE_MODEL].resoudre(['A'])
        self.assertIn('Contrat electricore obsolète', str(cm.exception))


@tagged('souscriptions', 'souscriptions_rsc_service', 'post_install', '-at_install')
class TestActionResoudreRscMaintenant(SouscriptionsTestCase):
    """Le bouton « résoudre la RSC maintenant » sur la Souscription."""

    def test_succes_ecrit_la_rsc_et_trace_au_chatter(self):
        self.souscription_base.id_affaire = '38233180'
        with _patch_appeler(return_value=[resultat_rsc('38233180', rsc='RSC-9001')]):
            self.souscription_base.action_resoudre_rsc_maintenant()

        self.assertEqual(self.souscription_base.ref_situation_contractuelle, 'RSC-9001')
        self.assertEqual(self.souscription_base.etat, 'en_service')
        self.assertFalse(self.souscription_base.motif_resolution_rsc)
        self.assertEqual(self.souscription_base.date_derniere_resolution_rsc, date.today())
        messages = self.souscription_base.message_ids.mapped('body')
        self.assertTrue(any('RSC-9001' in body for body in messages))

    def test_affaire_inconnue_stocke_le_motif_et_la_date(self):
        self.souscription_base.id_affaire = 'ZZZ999'
        with _patch_appeler(return_value=[resultat_rsc('ZZZ999', error='Affaire inconnue : ZZZ999')]):
            self.souscription_base.action_resoudre_rsc_maintenant()

        self.assertFalse(self.souscription_base.ref_situation_contractuelle)
        self.assertEqual(self.souscription_base.etat, 'en_instance')
        self.assertEqual(self.souscription_base.motif_resolution_rsc, 'Affaire inconnue : ZZZ999')
        self.assertEqual(self.souscription_base.date_derniere_resolution_rsc, date.today())

    def test_lot_mixte_et_desordre_contenu_envoye_verifie(self):
        """Deux Souscriptions résolues en un seul appel batch ; la réponse
        désordonnée est correctement appariée, et le lot envoyé au service
        est exactement les deux id_affaire attendus."""
        self.souscription_base.id_affaire = 'AFF-BASE'
        self.souscription_hphc.id_affaire = 'AFF-HPHC'
        motif_sans_c15 = (
            'Affaire connue (X12) sans situation contractuelle C15 (précurseur en cours ou affaire non contractuelle).'
        )
        reponse = [
            resultat_rsc('AFF-HPHC', error=motif_sans_c15),
            resultat_rsc('AFF-BASE', rsc='RSC-BASE-1'),
        ]
        souscriptions = self.souscription_base + self.souscription_hphc
        with _patch_appeler(return_value=reponse) as mock_appeler:
            souscriptions.action_resoudre_rsc_maintenant()

        mock_appeler.assert_called_once_with(['AFF-BASE', 'AFF-HPHC'])
        self.assertEqual(self.souscription_base.ref_situation_contractuelle, 'RSC-BASE-1')
        self.assertTrue(self.souscription_hphc.motif_resolution_rsc.startswith('Affaire connue'))

    def test_idempotence_souscription_en_service_jamais_reciblee(self):
        """Une Souscription déjà en service n'est jamais re-ciblée : aucun
        appel si le lot filtré est vide."""
        self.souscription_base.with_context(rsc_automatisme=True).write({'ref_situation_contractuelle': 'RSC-DEJA'})
        self.assertEqual(self.souscription_base.etat, 'en_service')

        with _patch_appeler() as mock_appeler:
            self.souscription_base.action_resoudre_rsc_maintenant()
        mock_appeler.assert_not_called()

    def test_souscription_resiliee_jamais_reciblee(self):
        """#136 : une Souscription résiliée n'est jamais re-ciblée par
        l'action serveur, même sans RSC (résiliation avant mise en service)
        et même appelée en lot — aucun appel au service RSC, idempotence
        conservée (même garde que le poll quotidien #89, `etat ==
        'en_instance'`). Clôture soldée (non-lissé, écarts nuls par
        construction, ADR 0031 décision 3, #247) : la Période contenant
        `date_fin` facturée suffit à faire basculer directement en
        `resiliee`, sans Régularisation."""
        self.env['souscription.periode'].create(
            {
                'souscription_id': self.souscription_base.id,
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 2, 1),
                'facture_legacy_ref': 'LEGACY-RESILIEE-GUARD-1',
            }
        )
        self.souscription_base.write({'date_fin': date(2024, 1, 31)})
        self.assertEqual(self.souscription_base.etat, 'resiliee')

        with _patch_appeler() as mock_appeler:
            self.souscription_base.action_resoudre_rsc_maintenant()
        mock_appeler.assert_not_called()

    def test_id_affaire_manquant_leve_userror_sans_appel(self):
        self.assertFalse(self.souscription_base.id_affaire)
        with _patch_appeler() as mock_appeler:
            with self.assertRaises(UserError):
                self.souscription_base.action_resoudre_rsc_maintenant()
        mock_appeler.assert_not_called()

    def test_version_inattendue_naucune_ecriture(self):
        self.souscription_base.id_affaire = '38233180'
        with _patch_appeler(side_effect=service_module.ContractVersionError('serveur v2 < attendu v3')):
            with self.assertRaises(UserError):
                self.souscription_base.action_resoudre_rsc_maintenant()

        self.assertFalse(self.souscription_base.ref_situation_contractuelle)
        self.assertFalse(self.souscription_base.motif_resolution_rsc)
        self.assertEqual(self.souscription_base.etat, 'en_instance')
