"""Unités de facturation : énergie en kWh, abonnement en jours (#304).

Les produits legacy facturent en `kg` (placeholder) / `Units` : une ligne de
facture d'énergie se lisait « 1234 kg » au lieu de « 1234 kWh ». Deux surfaces :

- AC1 : une installation NEUVE résout directement les bonnes unités sur le
  produit (`data/produits_energie.xml`, `data/produits_abonnement_simple.xml`) ;
- AC2 : la ligne de facture porte l'unité via `product_uom_id`
  (`souscription.periode._composer_lignes`), pas le produit. Odoo interdit de
  changer l'unité d'un produit déjà présent sur des écritures comptabilisées
  (`account._check_uom_not_in_invoice`), et les produits legacy restent en kg —
  mais chaque ligne générée affiche kWh / jour, sans écraser le prix unitaire ni
  toucher `product.uom_id` (les factures déjà émises gardent donc leur unité).
"""

from odoo.tests.common import TransactionCase, tagged

from .common import SouscriptionsTestCase

PRODUITS_ENERGIE = (
    'souscriptions_product_energie_base',
    'souscriptions_product_energie_hp',
    'souscriptions_product_energie_hc',
    'souscriptions_product_energie_base_solidaire',
    'souscriptions_product_energie_hp_solidaire',
    'souscriptions_product_energie_hc_solidaire',
)
PRODUITS_ABONNEMENT = (
    'souscriptions_product_abonnement_standard',
    'souscriptions_product_abonnement_solidaire',
)


@tagged('souscriptions', 'souscriptions_catalogue', 'post_install', '-at_install')
class TestUnitesFacturationInstallNeuve(TransactionCase):
    """AC1 : install fraîche — la data pointe déjà sur les bonnes unités."""

    def _ref(self, xmlid):
        return self.env.ref(f'souscriptions_odoo.{xmlid}')

    def test_produits_energie_en_kwh(self):
        kwh = self.env.ref('uom.product_uom_kwh')
        for xmlid in PRODUITS_ENERGIE:
            self.assertEqual(self._ref(xmlid).uom_id, kwh, f'{xmlid} doit être en kWh')

    def test_produits_abonnement_en_jours(self):
        jour = self.env.ref('uom.product_uom_day')
        for xmlid in PRODUITS_ABONNEMENT:
            self.assertEqual(self._ref(xmlid).uom_id, jour, f'{xmlid} doit être en jours')


@tagged('souscriptions', 'souscriptions_catalogue', 'post_install', '-at_install')
class TestUnitesFacturationLignes(SouscriptionsTestCase):
    """AC2 : la ligne générée porte kWh (énergie) / jour (abonnement), quelle que
    soit l'unité du produit, sans écraser le prix unitaire."""

    def _lignes_produit(self, facture):
        return facture.invoice_line_ids.filtered(lambda ligne: ligne.display_type == 'product')

    def test_lignes_portent_kwh_et_jours(self):
        periode = self.create_test_periode(self.souscription_base)
        facture = periode._creer_facture()
        kwh = self.env.ref('uom.product_uom_kwh')
        jour = self.env.ref('uom.product_uom_day')
        abo = self.env.ref('souscriptions_odoo.souscriptions_product_abonnement_standard')

        lignes = self._lignes_produit(facture)
        self.assertTrue(lignes, 'la facture doit porter des lignes produit')
        for ligne in lignes:
            attendue = jour if ligne.product_id == abo else kwh
            self.assertEqual(ligne.product_uom_id, attendue, f'{ligne.name} : unité inattendue')

    def test_ligne_energie_conserve_le_prix_grille(self):
        """Le prix unitaire (€/kWh de la grille) n'est PAS écrasé par une
        conversion produit→ligne (les produits ont un `list_price` nul : une
        conversion donnerait 0)."""
        periode = self.create_test_periode(self.souscription_base)
        facture = periode._creer_facture()
        base = self.env.ref('souscriptions_odoo.souscriptions_product_energie_base')
        ligne = facture.invoice_line_ids.filtered(lambda ligne: ligne.product_id == base)
        self.assertTrue(ligne, 'ligne énergie base attendue')
        self.assertEqual(ligne.price_unit, 0.15, 'prix_base de la grille de test')

    def test_produit_legacy_en_kg_facture_quand_meme_en_kwh(self):
        """Cas prod réel : un produit resté en kg (data `noupdate`, jamais migré
        — car Odoo l'interdit sur un produit déjà facturé) est facturé en kWh via
        la ligne, sans déclencher `account._check_uom_not_in_invoice` ni changer
        l'unité du produit."""
        base = self.env.ref('souscriptions_odoo.souscriptions_product_energie_base')
        kg = self.env.ref('uom.product_uom_kgm')
        kwh = self.env.ref('uom.product_uom_kwh')
        base.uom_id = kg  # simule un produit legacy non migré (aucune écriture postée ici)

        periode = self.create_test_periode(self.souscription_base)
        facture = periode._creer_facture()

        ligne = facture.invoice_line_ids.filtered(lambda ligne: ligne.product_id == base)
        self.assertTrue(ligne, 'ligne énergie base attendue')
        self.assertEqual(ligne.product_uom_id, kwh, 'la ligne affiche kWh malgré un produit en kg')
        self.assertEqual(ligne.price_unit, 0.15, 'prix grille préservé malgré la divergence kg→kWh')
        self.assertEqual(base.uom_id, kg, 'le produit legacy reste en kg — jamais touché')
