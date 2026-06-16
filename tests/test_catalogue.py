"""Catalogue *Produit de facturation* (`souscription.produit`).

Résout un *rôle de facturation* (abonnement / énergie / refacturation) vers le
`product.product` Odoo qui porte le compte + la TVA, dans l'**univers** standard
ou solidaire. L'isolation standard/solidaire est légale et structurelle (ADR 0013) :
aucun rôle ne doit résoudre vers le même produit dans les deux univers.

Surface de test = l'interface du catalogue, pas les composeurs qui l'appellent.
"""

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('souscriptions', 'souscriptions_catalogue', 'post_install', '-at_install')
class TestCatalogueProduit(TransactionCase):
    def _ref(self, xmlid):
        return self.env.ref(f'souscriptions_odoo.{xmlid}')

    def test_abonnement_resout_standard_et_solidaire(self):
        """Le rôle abonnement résout deux produits distincts selon l'univers."""
        catalogue = self.env['souscription.produit']
        std = catalogue.produit_abonnement(is_solidaire=False)
        sol = catalogue.produit_abonnement(is_solidaire=True)

        self.assertEqual(std, self._ref('souscriptions_product_abonnement_standard'))
        self.assertEqual(sol, self._ref('souscriptions_product_abonnement_solidaire'))
        self.assertNotEqual(std, sol)  # isolation : deux univers distincts (ADR 0013)

    def test_energie_resout_chaque_cadran_dans_les_deux_univers(self):
        """Chaque cadran facturé (base/hp/hc) résout vers le produit de l'univers
        demandé ; standard et solidaire ne se croisent jamais (ADR 0013)."""
        catalogue = self.env['souscription.produit']
        for cadran in ('base', 'hp', 'hc'):
            std = catalogue.produit_energie(cadran, is_solidaire=False)
            sol = catalogue.produit_energie(cadran, is_solidaire=True)
            self.assertEqual(std, self._ref(f'souscriptions_product_energie_{cadran}'))
            self.assertEqual(sol, self._ref(f'souscriptions_product_energie_{cadran}_solidaire'))
            self.assertNotEqual(std, sol)

    def test_refacturation_resout_chaque_nature_dans_les_deux_univers(self):
        """Chaque nature de refacturation (prestation/indemnité) résout vers le
        produit de l'univers demandé ; les deux univers restent isolés (ADR 0013)."""
        catalogue = self.env['souscription.produit']
        attendu = {
            'prestation': 'souscriptions_product_prestation_enedis',
            'indemnite': 'souscriptions_product_indemnite_enedis',
        }
        for nature, xmlid_std in attendu.items():
            std = catalogue.produit_refacturation(nature, is_solidaire=False)
            sol = catalogue.produit_refacturation(nature, is_solidaire=True)
            self.assertEqual(std, self._ref(xmlid_std))
            self.assertEqual(sol, self._ref(f'{xmlid_std}_solidaire'))
            self.assertNotEqual(std, sol)

    def test_cle_inconnue_leve_usererror(self):
        """Une clé de rôle inconnue (cadran / nature) lève UserError plutôt que de
        résoudre silencieusement vers le mauvais produit."""
        catalogue = self.env['souscription.produit']
        with self.assertRaises(UserError):
            catalogue.produit_energie('inexistant', is_solidaire=False)
        with self.assertRaises(UserError):
            catalogue.produit_refacturation('inexistante', is_solidaire=True)

    def test_produits_requis_12_produits_isoles(self):
        """produits_requis() résout tout le catalogue : 6 rôles × 2 univers = 12
        produits, tous distincts. Un produit partagé entre les univers ferait
        chuter le compte sous 12 — donc ce test garde l'isolation (ADR 0013)."""
        requis = self.env['souscription.produit'].produits_requis()
        self.assertEqual(len(requis), 12)
