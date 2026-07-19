"""Libellé de l'unité kWh (#307, sous-tâche d'affichage de #304).

Le mécanisme qui pose `product_uom_id` sur les lignes de facture est traité
par #306 (`tests/test_unites_facturation.py`). Reste un gap de LIBELLÉ : le
core Odoo 19 livre `uom.product_uom_kwh.name` = `KWH` en en_US ET fr_FR (la
traduction fr_FR vaut littéralement `KWH` — écrire seulement en_US ne
suffit pas). `uom.product_uom_day` est déjà correct (« Jours » en fr_FR),
rien à faire de ce côté.

`data/uom_libelle_kwh.xml` force le libellé à `kWh` (symbole SI, correct
dans toute langue) pour en_US et fr_FR via `update_field_translations`,
sans `noupdate` : rejoue à chaque `-i` ET `-u` pour survivre à un module
update sur une base déjà installée.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged('souscriptions', 'souscriptions_catalogue', 'post_install', '-at_install')
class TestUomLibelleKwh(TransactionCase):
    def test_libelle_kwh_en_us(self):
        kwh = self.env.ref('uom.product_uom_kwh')
        self.assertEqual(kwh.with_context(lang='en_US').name, 'kWh')

    def test_libelle_kwh_fr_fr(self):
        # fr_FR n'est pas forcément active sur une base de test fraîche —
        # la data elle-même l'active (cf. data/uom_libelle_kwh.xml), mais on
        # le refait ici pour ne pas dépendre de l'ordre de chargement.
        self.env['res.lang']._activate_lang('fr_FR')
        kwh = self.env.ref('uom.product_uom_kwh')
        self.assertEqual(kwh.with_context(lang='fr_FR').name, 'kWh')

    def test_jour_deja_correct_non_touche(self):
        """Non-régression : `uom.product_uom_day` n'est pas dans le champ
        d'application de #307, il était déjà correct."""
        self.env['res.lang']._activate_lang('fr_FR')
        jour = self.env.ref('uom.product_uom_day')
        self.assertEqual(jour.with_context(lang='fr_FR').name, 'Jours')

    def test_replay_de_la_donnee_est_idempotent(self):
        """Simule un `-u` : rejouer `update_field_translations` avec les
        mêmes valeurs ne doit pas régresser — c'est ce qui doit se produire
        à chaque mise à jour du module (pas de noupdate sur ce fichier)."""
        self.env['res.lang']._activate_lang('fr_FR')
        kwh = self.env.ref('uom.product_uom_kwh')
        kwh.update_field_translations('name', {'en_US': 'kWh', 'fr_FR': 'kWh'})
        self.assertEqual(kwh.with_context(lang='en_US').name, 'kWh')
        self.assertEqual(kwh.with_context(lang='fr_FR').name, 'kWh')
