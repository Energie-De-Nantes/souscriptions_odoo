"""Tests #147 — sync electricore des prestations : pull-tout, insert-si-absente.

Couture de test (socle commun #222) : `_tirer_prestations` (transport JSONL)
est patchée avec des lignes en boîte (contrat v1 `PrestationF15`, dicts
plats) ; la fabrique client est patchée pour rendre un MagicMock (sa garde
paquet/config est testée dans test_electricore_client_fabrique.py).
Résolution RSC, mapping nature et insert-si-absente restent réels. Aucun
HTTP.

Décisions du grill 2026-07-08 (cf. issue #147) : résolution par RSC seule
(pas de repli PDL, ADR 0010 §4), insert-si-absente (pas de chemin d'update —
la *Référence de contenu* EST le contenu), `montant_ht` ignoré.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from odoo.addons.souscriptions_odoo.models.core import souscription_refacturation as refacturation_module
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase, flux_electricore, patcher_client_fabrique, patcher_transport


def _ligne(**overrides):
    """Stub d'une ligne du contrat v1 `PrestationF15` (dict plat)."""
    base = dict(
        reference='ref-0001',
        pdl='PDL_TEST_STANDARD',
        ref_situation_contractuelle='RSC_SYNC_BASE',
        id_ev='F180B',
        nature_ev='01',
        libelle_ev='Mise en service',
        taux_tva_applicable='20.00',
        prix_unitaire=30.37,
        quantite=1.0,
        montant_ht=30.37,
        date_debut='2025-02-03',
        date_fin='2025-02-03',
        num_facture='3210619182010',
        date_facture='2025-02-05',
    )
    base.update(overrides)
    return base


def _presta_stream(*lignes):
    """Flux factice de `PrestationF15` : objets à `.model_dump()` (contrat v1
    réel), pas des dicts plats — `_tirer_prestations` appelle `.model_dump()`
    sur chaque élément du flux."""
    return flux_electricore([SimpleNamespace(model_dump=lambda l=l: l) for l in lignes])


@tagged('souscriptions', 'souscriptions_sync_prestations', 'post_install', '-at_install')
class TestSyncPrestations(SouscriptionsTestCase):
    def setUp(self):
        super().setUp()
        self.fake_client = MagicMock(url='https://electricore.example.test', api_key='fake-api-key')
        patcher = patcher_client_fabrique(self.fake_client)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC_SYNC_BASE'}
        )
        self.Refacturation = self.env['souscription.refacturation']

    def _sync(self, lignes):
        with patcher_transport(
            refacturation_module.SouscriptionRefacturation, '_tirer_prestations', return_value=lignes
        ):
            return self.Refacturation.synchroniser_depuis_electricore()

    def _prestas(self, reference):
        return self.Refacturation.search([('reference', '=', reference)])

    def test_pull_cree_et_classe_la_nature(self):
        """Taux 'NS' -> indemnité (hors champ TVA) ; taux numérique -> prestation taxée.
        La TVA suit le produit choisi par la nature (ADR 0009 §5), jamais la ligne."""
        action = self._sync(
            [
                _ligne(reference='ref-mes', taux_tva_applicable='20.00'),
                _ligne(
                    reference='ref-pen',
                    id_ev='DCOUP_PEN',
                    libelle_ev='Pénalité pour coupure réseau',
                    taux_tva_applicable='NS',
                    prix_unitaire=-24.0,
                    quantite=2.0,
                ),
            ]
        )

        mes = self._prestas('ref-mes')
        pen = self._prestas('ref-pen')
        self.assertEqual(mes.nature, 'prestation')
        self.assertEqual(mes.souscription_id, self.souscription_base)  # résolu par RSC
        self.assertEqual(pen.nature, 'indemnite')
        self.assertEqual(pen.prix, -24.0)
        self.assertEqual(pen.quantite, 2.0)
        self.assertEqual(pen.code_enedis, 'DCOUP_PEN')
        self.assertIn('2 créée(s)', action['params']['message'])

    def test_taux_null_ou_vide_classe_indemnite(self):
        """Régression : l'API prestations renvoie des DCOUP_PEN à `taux_tva_applicable`
        null. Un null (ou vide) ne doit JAMAIS retomber sur 'prestation' — sinon on
        facture de la TVA sur une pénalité hors champ. Seul un taux numérique taxe."""
        self._sync(
            [
                _ligne(reference='ref-null', id_ev='DCOUP_PEN', taux_tva_applicable=None),
                _ligne(reference='ref-vide', id_ev='DCOUP_PEN', taux_tva_applicable=''),
            ]
        )
        self.assertEqual(self._prestas('ref-null').nature, 'indemnite')
        self.assertEqual(self._prestas('ref-vide').nature, 'indemnite')

    def test_rerun_idempotent_zero_creation_zero_write(self):
        """AC1 : 2ᵉ run = 0 création, 0 write — insert-si-absente, aucun chemin
        d'update. Même un payload amont différent à référence constante ne touche
        pas la ligne existante (même référence = même contenu par construction ;
        l'échappatoire est de supprimer la ligne non facturée et resynchroniser)."""
        self._sync([_ligne(reference='ref-idem', prix_unitaire=30.37)])
        action = self._sync([_ligne(reference='ref-idem', prix_unitaire=999.99)])

        presta = self._prestas('ref-idem')
        self.assertEqual(len(presta), 1)
        self.assertEqual(presta.prix, 30.37)
        self.assertIn('0 créée(s)', action['params']['message'])

    def test_resolution_rsc_seule_pas_de_repli_pdl(self):
        """RSC inconnue -> ignorée et comptée, même si le PDL matcherait une
        souscription (aucun repli flou sur le flux vif, ADR 0010 §4). Signal de
        backfill RSC : la ligne est rattrapée gratuitement au run suivant."""
        action = self._sync(
            [
                _ligne(
                    reference='ref-orpheline',
                    pdl='PDL_TEST_STANDARD',  # PDL de souscription_base — ne doit PAS servir
                    ref_situation_contractuelle='RSC_INCONNUE',
                ),
                _ligne(reference='ref-sans-rsc', ref_situation_contractuelle=None),
            ]
        )

        self.assertFalse(self._prestas('ref-orpheline'))
        self.assertFalse(self._prestas('ref-sans-rsc'))
        self.assertIn('2 sans souscription', action['params']['message'])

    def test_rsc_backfillee_rattrapee_au_run_suivant(self):
        """Une ligne ignorée (RSC inconnue) est matérialisée au run suivant une
        fois la RSC posée sur la souscription — le pull-tout la représente."""
        self._sync([_ligne(reference='ref-backfill', ref_situation_contractuelle='RSC_SYNC_HPHC')])
        self.assertFalse(self._prestas('ref-backfill'))

        self.souscription_hphc.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC_SYNC_HPHC'}
        )
        self._sync([_ligne(reference='ref-backfill', ref_situation_contractuelle='RSC_SYNC_HPHC')])

        self.assertEqual(self._prestas('ref-backfill').souscription_id, self.souscription_hphc)

    def test_arrivee_tardive_materialisee(self):
        """Pull-tout sans curseur (ADR 0009 §2) : une ligne F15 datée dans le
        passé, absente du premier run, est matérialisée au run suivant."""
        self._sync([_ligne(reference='ref-t1')])
        self._sync(
            [
                _ligne(reference='ref-t1'),
                _ligne(reference='ref-tardive', date_debut='2024-01-05', date_facture='2024-02-05'),
            ]
        )

        self.assertEqual(len(self._prestas('ref-tardive')), 1)

    def test_facturee_jamais_touchee(self):
        """Gel des facturées automatique (ADR 0009 §4) : une référence existante
        n'est jamais réécrite, facture posée ou non."""
        self._sync([_ligne(reference='ref-gelee', prix_unitaire=30.37)])
        presta = self._prestas('ref-gelee')
        _periode, facture = self.create_test_invoice(self.souscription_base)
        presta.facture_id = facture

        self._sync([_ligne(reference='ref-gelee', prix_unitaire=999.99)])

        self.assertEqual(presta.prix, 30.37)
        self.assertEqual(presta.facture_id, facture)

    def test_erreur_par_ligne_ne_bloque_pas_le_lot(self):
        """Skip-and-report par ligne (ADR 0011) : une contrainte (ici UNIQUE sur
        une référence dupliquée dans le même lot — violation du contrat v1) est
        absorbée par le savepoint, comptée, et n'emporte pas les autres lignes."""
        action = self._sync(
            [
                _ligne(reference='ref-dup'),
                _ligne(reference='ref-dup', prix_unitaire=999.99),
                _ligne(reference='ref-autre'),
            ]
        )

        self.assertEqual(len(self._prestas('ref-dup')), 1)
        self.assertTrue(self._prestas('ref-autre'))
        self.assertIn('1 en erreur', action['params']['message'])

    def test_contract_version_error_mappee_en_userror(self):
        """Contrat obsolète -> erreur dure actionnable (UserError), pas de
        traceback brut pour le·la facturiste."""
        with patcher_transport(
            refacturation_module.SouscriptionRefacturation,
            '_tirer_prestations',
            side_effect=refacturation_module.ContractVersionError('serveur v0 < attendu v1'),
        ):
            with self.assertRaises(UserError) as cm:
                self.Refacturation.synchroniser_depuis_electricore()
        self.assertIn('v0', str(cm.exception))


@tagged('souscriptions', 'souscriptions_sync_prestations', 'post_install', '-at_install')
class TestTirerPrestations(SouscriptionsTestCase):
    """`_tirer_prestations` elle-même (#245) : périmètre Enedis potentiellement
    partagé entre entités — la requête ne doit demander que les RSC de nos
    souscriptions, chunkée si le lot est gros (le paramètre `rsc` part en
    query string GET, cf. `ElectricoreClient.prestations`). Client mocké
    directement (méthode transport, pas la fabrique) : aucun HTTP."""

    def setUp(self):
        super().setUp()
        self.Refacturation = self.env['souscription.refacturation']
        self.souscription_base.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC_SYNC_BASE'}
        )
        self.souscription_hphc.with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': 'RSC_SYNC_HPHC'}
        )

    def test_filtre_sur_les_rsc_de_nos_souscriptions(self):
        """AC1 (#245) : la requête ne demande que les RSC de nos souscriptions
        — sans le filtre, on tirerait sur le fil les prestations d'un tiers
        partageant le périmètre Enedis, pour les jeter à l'insertion."""
        client = MagicMock()
        client.prestations.side_effect = lambda **kwargs: _presta_stream()

        self.Refacturation._tirer_prestations(client)

        rsc_demandees = client.prestations.call_args.kwargs['rsc']
        self.assertCountEqual(rsc_demandees, ['RSC_SYNC_BASE', 'RSC_SYNC_HPHC'])

    def test_aucune_rsc_resolue_naboutit_pas_a_un_appel(self):
        """Aucune souscription à RSC résolue -> aucun round-trip réseau (même
        fast-fail que le pull méta-périodes, #245)."""
        (self.souscription_base | self.souscription_hphc).with_context(rsc_automatisme=True).write(
            {'ref_situation_contractuelle': False}
        )
        client = MagicMock()

        lignes = self.Refacturation._tirer_prestations(client)

        client.prestations.assert_not_called()
        self.assertEqual(lignes, [])

    def test_chunk_le_pull_par_lots_et_fusionne_les_flux(self):
        """Point d'attention #245 : ~1 000 RSC en query string GET — chunké
        par lots de `TAILLE_LOT_RSC`, les flux de chaque lot sont fusionnés.
        Lot forcé à 1 ici pour exercer le chunking sans créer 150+ souscriptions."""
        lignes_par_rsc = {
            'RSC_SYNC_BASE': _ligne(reference='ref-base', ref_situation_contractuelle='RSC_SYNC_BASE'),
            'RSC_SYNC_HPHC': _ligne(reference='ref-hphc', ref_situation_contractuelle='RSC_SYNC_HPHC'),
        }
        client = MagicMock()
        client.prestations.side_effect = lambda *, rsc: _presta_stream(*(lignes_par_rsc[r] for r in rsc))

        with patch.object(refacturation_module, 'TAILLE_LOT_RSC', 1):
            lignes = self.Refacturation._tirer_prestations(client)

        self.assertEqual(client.prestations.call_count, 2)
        lots_demandes = [call.kwargs['rsc'] for call in client.prestations.call_args_list]
        self.assertEqual([len(lot) for lot in lots_demandes], [1, 1])
        self.assertEqual({ligne['reference'] for ligne in lignes}, {'ref-base', 'ref-hphc'})
