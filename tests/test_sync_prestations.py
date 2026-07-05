"""Tests #37 — sync electricore des prestations : pull-tout, dédup par référence Enedis.

Couture de test : `_tirer_prestations` (transport JSONL) est patchée avec des
lignes en boîte (contrat v1 `PrestationF15`, dicts plats) ; la fabrique client
est patchée pour rendre un MagicMock (sa garde paquet/config est testée dans
test_electricore_client_fabrique.py). Résolution RSC/PDL, mapping nature et
upsert restent réels. Aucun HTTP.
"""

from unittest.mock import MagicMock, patch

from odoo.addons.souscriptions_odoo.models.core import electricore_client_fabrique as fabrique_module
from odoo.addons.souscriptions_odoo.models.core import souscription_refacturation as refacturation_module
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


def _ligne(**overrides):
    """Stub d'une ligne du contrat v1 `PrestationF15` (dict plat)."""
    base = dict(
        reference='ref-0001',
        pdl='PDL_TEST_STANDARD',
        ref_situation_contractuelle=None,
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


@tagged('souscriptions', 'souscriptions_sync_prestations', 'post_install', '-at_install')
class TestSyncPrestations(SouscriptionsTestCase):
    def setUp(self):
        super().setUp()
        self.fake_client = MagicMock(url='https://electricore.example.test', api_key='fake-api-key')
        patcher = patch.object(fabrique_module.SouscriptionElectricoreClient, 'client', return_value=self.fake_client)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.Refacturation = self.env['souscription.refacturation']

    def _sync(self, lignes):
        with patch.object(refacturation_module.SouscriptionRefacturation, '_tirer_prestations', return_value=lignes):
            return self.Refacturation.synchroniser_depuis_electricore()

    def _prestas(self, reference):
        return self.Refacturation.search([('reference_enedis', '=', reference)])

    def test_pull_cree_et_classe_la_nature(self):
        """Taux 'NS' -> indemnité (hors champ TVA) ; taux numérique -> prestation taxée.
        La TVA suit le produit choisi par la nature (ADR 0009 §5), jamais la ligne."""
        self._sync(
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
        self.assertEqual(pen.nature, 'indemnite')
        self.assertEqual(pen.prix, -24.0)
        self.assertEqual(pen.quantite, 2.0)
        self.assertEqual(pen.code_enedis, 'DCOUP_PEN')
        self.assertEqual(mes.souscription_id, self.souscription_base)  # résolu par PDL

    def test_rerun_idempotent_par_reference(self):
        """Deux runs identiques : aucun doublon (dédup par contrainte UNIQUE + upsert)."""
        lignes = [_ligne(reference='ref-idem')]
        self._sync(lignes)
        self._sync(lignes)

        self.assertEqual(len(self._prestas('ref-idem')), 1)

    def test_resolution_rsc_prioritaire_sur_pdl(self):
        """La RSC identifie LE contrat : une prestation d'un ancien contrat sur le
        même PDL ne doit pas atterrir sur le contrat courant."""
        ancien = (
            self.env['souscription.souscription']
            .with_context(rsc_automatisme=True)
            .create(
                {
                    'partner_id': self.partner_test.id,
                    'pdl': 'PDL_TEST_STANDARD',  # même PDL que souscription_base
                    'puissance_souscrite': '6',
                    'type_tarif': 'base',
                    'etat_facturation_id': self.etat_facturation.id,
                    'ref_situation_contractuelle': 'RSC_SYNC_ANCIEN',
                }
            )
        )

        self._sync([_ligne(reference='ref-rsc', ref_situation_contractuelle='RSC_SYNC_ANCIEN')])

        self.assertEqual(self._prestas('ref-rsc').souscription_id, ancien)

    def test_pdl_ambigu_ou_inconnu_ignore(self):
        """Sans RSC : PDL porté par deux souscriptions non résiliées = ambigu, ignoré ;
        PDL inconnu = ignoré. Rien n'est matérialisé (v1, skip-and-report)."""
        self.env['souscription.souscription'].create(
            {
                'partner_id': self.partner_test.id,
                'pdl': 'PDL_TEST_STANDARD',  # doublon de PDL avec souscription_base
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'etat_facturation_id': self.etat_facturation.id,
            }
        )

        self._sync(
            [
                _ligne(reference='ref-ambigu'),  # PDL_TEST_STANDARD, désormais porté 2×
                _ligne(reference='ref-orphelin', pdl='PDL_INCONNU'),
            ]
        )

        self.assertFalse(self._prestas('ref-ambigu'))
        self.assertFalse(self._prestas('ref-orphelin'))

    def test_arrivee_tardive_materialisee(self):
        """Pull-tout sans curseur : une ligne F15 datée dans le passé, absente du
        premier run, est matérialisée au run suivant."""
        self._sync([_ligne(reference='ref-t1')])
        self._sync(
            [
                _ligne(reference='ref-t1'),
                _ligne(reference='ref-tardive', date_debut='2024-01-05', date_facture='2024-02-05'),
            ]
        )

        self.assertEqual(len(self._prestas('ref-tardive')), 1)

    def test_facturee_jamais_reecrite(self):
        """`facture_id` posé = prestation gelée : un changement amont ne la réécrit
        pas (la source de vérité du facturé est la facture, ADR 0009 §4)."""
        self._sync([_ligne(reference='ref-gelee', prix_unitaire=30.37)])
        presta = self._prestas('ref-gelee')
        _periode, facture = self.create_test_invoice(self.souscription_base)
        presta.facture_id = facture

        self._sync([_ligne(reference='ref-gelee', prix_unitaire=999.99)])

        self.assertEqual(presta.prix, 30.37)
