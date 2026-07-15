"""Unités de facturation : énergie en kWh, abonnement en jours (#304).

Les 6 produits d'énergie (Base/HP/HC × standard/solidaire) pointaient sur
`kg` (placeholder) et les 2 produits d'abonnement n'avaient pas d'unité
(défaut Odoo `Units`) : une ligne de facture d'énergie se lisait
« 1234 kg » au lieu de « 1234 kWh ». Deux surfaces à couvrir :

- AC1 : une installation neuve résout directement les bonnes unités
  (`data/produits_energie.xml`, `data/produits_abonnement_simple.xml`) ;
- AC2 : le helper de migration `_repointer_unites`
  (`migrations/19.0.1.18.0/post-migrate.py`, pour les 8 produits déjà en
  prod) est idempotent et gardé — il ne re-pointe que ce qui est encore sur
  le placeholder d'origine, jamais un choix manuel déjà fait.

Chargé par chemin (`runpy.run_path`, même idiome que
`test_migration_energie_facturee.py` / `test_releve.py` : le dossier de
version n'est pas un identifiant Python importable) et appelé directement
sur le helper `_repointer_unites(env)` — pas `migrate(cr, version)` — pour
tester la logique sans passer par le SQL brut de `api.Environment`.
"""

import os
import runpy

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


@tagged('souscriptions', 'souscriptions_migration', 'post_install', '-at_install')
class TestMigrationUnitesFacturation(SouscriptionsTestCase):
    """AC2 : le helper de migration `_repointer_unites` est idempotent et
    gardé sur le placeholder d'origine."""

    @staticmethod
    def _repointer(env):
        chemin = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'migrations', '19.0.1.18.0', 'post-migrate.py'
        )
        module = runpy.run_path(chemin)
        module['_repointer_unites'](env)

    def test_energie_idempotent_repointe_puis_rejoue_sans_effet(self):
        produit = self.env.ref('souscriptions_odoo.souscriptions_product_energie_base')
        kg = self.env.ref('uom.product_uom_kgm')
        kwh = self.env.ref('uom.product_uom_kwh')
        produit.uom_id = kg

        self._repointer(self.env)
        produit.invalidate_recordset()
        self.assertEqual(produit.uom_id, kwh)

        self._repointer(self.env)  # rejoué : déjà en kWh — no-op
        produit.invalidate_recordset()
        self.assertEqual(produit.uom_id, kwh)

    def test_abonnement_idempotent_repointe_puis_rejoue_sans_effet(self):
        produit = self.env.ref('souscriptions_odoo.souscriptions_product_abonnement_standard')
        unite = self.env.ref('uom.product_uom_unit')
        jour = self.env.ref('uom.product_uom_day')
        produit.uom_id = unite

        self._repointer(self.env)
        produit.invalidate_recordset()
        self.assertEqual(produit.uom_id, jour)

        self._repointer(self.env)  # rejoué : déjà en jours — no-op
        produit.invalidate_recordset()
        self.assertEqual(produit.uom_id, jour)

    def test_guard_ne_touche_pas_une_unite_deliberement_differente(self):
        """Un produit déjà sur une TROISIÈME unité (choix manuel en prod, ni
        placeholder ni cible) n'est pas écrasé — le helper ne garde que le
        placeholder d'origine, jamais « tout ce qui n'est pas la cible »."""
        produit = self.env.ref('souscriptions_odoo.souscriptions_product_energie_base')
        autre = self.env.ref('uom.product_uom_unit')
        produit.uom_id = autre

        self._repointer(self.env)
        produit.invalidate_recordset()
        self.assertEqual(produit.uom_id, autre)
