"""Provenance des lignes de facture — générées miroir readonly, manuelles
préservées, enforcement doux (#266, tranche 2 du PRD #264, ADR 0014 amendé).

Couvre ce qui est transverse aux trois sources de composition (Période,
Refacturation, Régularisation) : le champ de provenance lui-même
(`copy=False`), la vue (readonly conditionnel dans `invoice_line_ids`), et la
migration de backfill. Les scénarios de re-génération à l'émission propres à
chaque source vivent dans `test_periode_facture.py`
(`TestPeriodeFactureRegenerationEmission`) et `test_regularisation_facture.py`
(`TestRegularisationFactureRegenerationEmission`) — prior art de #266.
"""

import os
import runpy
from datetime import date

from lxml import etree
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_provenance', 'post_install', '-at_install')
class TestLigneGenereeChamp(SouscriptionsTestCase):
    def test_champ_ligne_generee_copy_false(self):
        """AC #266 : `copy=False` sur le champ lui-même — garantie statique
        qu'aucun chemin de copie (avoir, duplication) ne peut le porter."""
        self.assertFalse(self.env['account.move.line']._fields['souscription_ligne_generee'].copy)

    def test_duplication_facture_ne_porte_pas_le_flag(self):
        """AC #266 : dupliquer une facture d'énergie postée ne reproduit pas
        le flag sur les lignes du duplicata (`copy=False`)."""
        periode = self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        facture = periode._creer_facture()
        facture.action_post()
        self.assertTrue(facture.invoice_line_ids.filtered('souscription_ligne_generee'))

        duplicata = facture.copy()

        self.assertFalse(duplicata.invoice_line_ids.filtered('souscription_ligne_generee'))

    def test_composer_ligne_refacturation_pose_le_flag(self):
        """`souscription.refacturation._composer_ligne` pose le flag lui-même
        (#266) — le chemin de rassemblement des Refacturations n'a rien à
        faire de plus."""
        presta = self.env['souscription.refacturation'].create(
            {
                'souscription_id': self.souscription_base.id,
                'reference': 'F15-PROV',
                'libelle': 'Déplacement',
                'prix': 45.0,
                'quantite': 1.0,
            }
        )
        _cmd, _id, vals = presta._composer_ligne()
        self.assertTrue(vals.get('souscription_ligne_generee'))


@tagged('souscriptions', 'souscriptions_provenance', 'post_install', '-at_install')
class TestLigneGenereeVueReadonly(SouscriptionsTestCase):
    """AC #266 : readonly conditionnel dans la vue formulaire — mécanisme
    Odoo standard (attribut readonly par champ dans la sous-liste
    `invoice_line_ids`), jamais une surcharge de `write()`."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        view = cls.env['account.move'].get_view(view_type='form')
        cls.arch = etree.fromstring(view['arch'])

    def test_champs_composes_readonly_conditionnel_dans_invoice_line_ids(self):
        conteneur = self.arch.find(".//field[@name='invoice_line_ids']")
        self.assertIsNotNone(conteneur, 'Le formulaire facture doit porter invoice_line_ids')

        for champ in ('product_id', 'name', 'quantity', 'price_unit'):
            noeuds = conteneur.findall(f".//field[@name='{champ}']")
            self.assertTrue(noeuds, f'Champ {champ} absent de la sous-liste invoice_line_ids')
            self.assertEqual(
                noeuds[0].get('readonly'),
                'souscription_ligne_generee',
                f'{champ} doit être readonly conditionnel à souscription_ligne_generee',
            )

    def test_flag_charge_dans_la_sous_liste(self):
        """Le champ de la condition doit être chargé (au moins en colonne
        invisible) pour que le readonly conditionnel soit évaluable par
        ligne."""
        conteneur = self.arch.find(".//field[@name='invoice_line_ids']")
        self.assertTrue(conteneur.findall(".//field[@name='souscription_ligne_generee']"))


@tagged('souscriptions', 'souscriptions_migration', 'souscriptions_provenance', 'post_install', '-at_install')
class TestMigrationProvenanceLignesGenerees(SouscriptionsTestCase):
    """Migration `19.0.1.16.0` : flague « générées » les lignes des factures
    d'énergie en BROUILLON existantes (#266). Même idiome que
    `test_migration_energie_facturee.py` (runpy, script SQL direct)."""

    @staticmethod
    def _migrer(cr):
        chemin = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'migrations', '19.0.1.16.0', 'post-migrate.py'
        )
        module = runpy.run_path(chemin)
        module['migrate'](cr, None)

    def _periode_facturee_sans_flag(self, souscription, **vals):
        """Périod facturée en brouillon dont les lignes ne portent PAS encore
        le flag — l'état pré-#266 que la migration doit réparer. Bâtie
        directement (pas via `_creer_facture`, qui flague déjà)."""
        base = {
            'souscription_id': souscription.id,
            'date_debut': date(2024, 1, 1),
            'date_fin': date(2024, 1, 31),
            'type_periode': 'mensuelle',
            'provision_base_kwh': 100.0,
        }
        base.update(vals)
        periode = self.env['souscription.periode'].create(base)
        produit = self.env.ref('souscriptions_odoo.souscriptions_product_energie_base')
        facture = self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': souscription.partner_id.id,
                'invoice_date': periode.date_fin,
                'periode_id': periode.id,
                'invoice_line_ids': [
                    (0, 0, {'display_type': 'line_section', 'name': 'Énergie'}),
                    (0, 0, {'product_id': produit.id, 'name': 'Énergie Base', 'quantity': 100.0, 'price_unit': 0.15}),
                ],
            }
        )
        return periode, facture

    def test_backfill_flague_les_lignes_du_brouillon(self):
        _periode, facture = self._periode_facturee_sans_flag(self.souscription_base)
        lignes = facture.invoice_line_ids
        self.assertFalse(any(lignes.mapped('souscription_ligne_generee')))

        self._migrer(self.env.cr)
        lignes.invalidate_recordset()

        self.assertTrue(all(lignes.mapped('souscription_ligne_generee')))

    def test_backfill_ignore_les_factures_postees(self):
        """Une facture déjà postée n'est pas concernée (l'enforcement doux ne
        s'applique qu'au brouillon ; une facture postée n'est jamais
        régénérée)."""
        _periode, facture = self._periode_facturee_sans_flag(
            self.souscription_base, date_debut=date(2024, 2, 1), date_fin=date(2024, 2, 29)
        )
        facture.action_post()
        lignes = facture.invoice_line_ids.filtered(lambda l: l.display_type in ('product', 'line_section'))

        self._migrer(self.env.cr)
        lignes.invalidate_recordset()

        self.assertFalse(any(lignes.mapped('souscription_ligne_generee')))

    def test_backfill_idempotent(self):
        _periode, facture = self._periode_facturee_sans_flag(
            self.souscription_base, date_debut=date(2024, 3, 1), date_fin=date(2024, 3, 31)
        )
        lignes = facture.invoice_line_ids

        self._migrer(self.env.cr)
        self._migrer(self.env.cr)  # rejoué : rien à corriger
        lignes.invalidate_recordset()

        self.assertTrue(all(lignes.mapped('souscription_ligne_generee')))
