"""
Validation des données de démo des relevés (#54-#57).

L'enjeu central est l'INVARIANT D'ORDRE DE CHARGEMENT : dans
`demo/souscriptions_demo.xml`, les relevés des périodes facturées doivent être
définis AVANT les factures (`account.move`) — sinon le verrou (#56) rejetterait
leur création et l'installation avec démo échouerait. Ce test lit le XML et
vérifie l'ordre, **sans dépendre** du chargement effectif de la démo (que le
runner de test n'active pas). Des contrôles « live » complètent si la démo est
présente.
"""

import os

from lxml import etree
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('souscriptions', 'souscriptions_releve', 'post_install', '-at_install')
class TestReleveDemoOrdre(TransactionCase):
    """Invariant structurel : tout relevé démo précède la 1re facture démo."""

    def test_releves_definis_avant_les_factures(self):
        demo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'demo', 'souscriptions_demo.xml')
        tree = etree.parse(demo_path)
        models_in_order = [rec.get('model') for rec in tree.iter('record')]

        self.assertIn('souscription.releve', models_in_order, 'Aucun relevé de démo trouvé')
        self.assertIn('account.move', models_in_order, 'Aucune facture de démo trouvée')

        derniere_releve = max(i for i, m in enumerate(models_in_order) if m == 'souscription.releve')
        premiere_facture = min(i for i, m in enumerate(models_in_order) if m == 'account.move')

        self.assertLess(
            derniere_releve,
            premiere_facture,
            'Les relevés de démo doivent être définis AVANT les factures, sinon le '
            "verrou (#56) ferait échouer l'installation avec démo.",
        )


@tagged('souscriptions', 'souscriptions_releve', 'post_install', '-at_install')
class TestReleveDemoLive(TransactionCase):
    """Contrôles sur la démo chargée (skippés si la base n'a pas la démo)."""

    def _ref(self, xmlid):
        return self.env.ref(f'souscriptions_odoo.{xmlid}', raise_if_not_found=False)

    def setUp(self):
        super().setUp()
        if not self._ref('demo_periode_janvier_admin'):
            self.skipTest('Données de démo non chargées sur cette base')

    def test_periode_non_facturee_a_des_releves_editables(self):
        periode = self._ref('demo_periode_janvier_base')
        self.assertFalse(periode.facture_id)
        self.assertTrue(periode.releve_ids)
        periode.releve_ids[0].index_base = 12345.0  # pas de verrou avant facture

    def test_periode_facturee_a_des_releves_figes(self):
        periode = self._ref('demo_periode_janvier_admin')
        self.assertTrue(periode.facture_id)
        self.assertTrue(periode.releve_ids)
        with self.assertRaises(UserError):
            periode.releve_ids[0].index_hph = 99999.0

    def test_changement_compteur_trois_releves(self):
        periode = self._ref('demo_periode_fevrier_base')
        self.assertEqual(len(periode.releve_ids), 3)

    def test_juin_2026_swap_compteur_affiche_union_base_et_4_cadrans(self):
        """Non-régression #138 : période démo « Juin 2026 » — Base facturée
        (config_cadrans hérité 'base'), mais relevée par deux familles (swap de
        compteur en cours de mois). Le justificatif doit afficher l'union
        (Base + HPH/HPB/HCH/HCB), pas Base seule comme le ferait l'ancienne
        lecture directe de config_cadrans."""
        periode = self._ref('demo_periode_juin_2026_swap_compteur')
        if not periode:
            self.skipTest('Données de démo non chargées sur cette base')
        self.assertEqual(periode.config_cadrans, 'base')

        self.assertEqual(
            [c['field'] for c in periode.releve_colonnes()],
            ['index_base', 'index_hph', 'index_hpb', 'index_hch', 'index_hcb'],
        )
        # Diff visuel de la transition : le relevé post-swap ne renseigne pas
        # index_base, qui reste donc à 0 sur cette ligne.
        releve_apres_swap = periode.releve_ids.sorted('date')[-1]
        self.assertEqual(releve_apres_swap.index_base, 0)
        self.assertEqual(releve_apres_swap.index_hph, 100)
