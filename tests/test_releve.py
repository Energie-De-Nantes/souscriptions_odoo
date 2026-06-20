"""
Relevés d'index (#54 / ADR 0015) : modèle enfant `souscription.releve` de la
Période, saisie backend. Forme large par cadran réseau, nature réel/estimé,
cardinalité variable. Pas de verrou ici (#56) ni de rendu (#55/#57).
"""

from datetime import date

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


@tagged('souscriptions', 'souscriptions_releve', 'post_install', '-at_install')
class TestReleveModel(SouscriptionsTestCase):
    def test_releve_base_persiste_et_se_lit_via_periode(self):
        """Un relevé Base créé sur une Période est lisible via periode.releve_ids."""
        periode = self.create_test_periode(self.souscription_base)

        releve = self.env['souscription.releve'].create(
            {
                'periode_id': periode.id,
                'date': date(2024, 1, 1),
                'nature': 'reel',
                'index_base': 12345.0,
            }
        )

        self.assertIn(releve, periode.releve_ids)
        self.assertEqual(releve.index_base, 12345.0)
        self.assertEqual(releve.nature, 'reel')

    def test_releve_hp_hc_porte_les_index_par_registre(self):
        """En config hp_hc, un relevé porte index_hp et index_hc."""
        # config_cadrans est figé sur la Période depuis la Souscription (ADR 0005).
        self.souscription_hphc.config_cadrans = 'hp_hc'
        periode = self.create_test_periode(self.souscription_hphc)

        releve = self.env['souscription.releve'].create(
            {
                'periode_id': periode.id,
                'date': date(2024, 1, 31),
                'nature': 'estime',
                'index_hp': 8000.0,
                'index_hc': 4000.0,
            }
        )

        self.assertEqual(releve.index_hp, 8000.0)
        self.assertEqual(releve.index_hc, 4000.0)
        self.assertEqual(releve.nature, 'estime')
        # config_cadrans est exposé (related) pour piloter l'affichage.
        self.assertEqual(releve.config_cadrans, 'hp_hc')

    def test_releve_4_cadrans_porte_les_quatre_index(self):
        """En config 4_cadrans, un relevé porte les 4 index saisonniers."""
        self.souscription_hphc.config_cadrans = '4_cadrans'
        periode = self.create_test_periode(self.souscription_hphc)

        releve = self.env['souscription.releve'].create(
            {
                'periode_id': periode.id,
                'date': date(2024, 1, 1),
                'nature': 'reel',
                'index_hph': 1000.0,
                'index_hpb': 2000.0,
                'index_hch': 3000.0,
                'index_hcb': 4000.0,
            }
        )

        self.assertEqual(
            (releve.index_hph, releve.index_hpb, releve.index_hch, releve.index_hcb),
            (1000.0, 2000.0, 3000.0, 4000.0),
        )
        self.assertEqual(releve.config_cadrans, '4_cadrans')

    def test_releves_ordonnes_chronologiquement(self):
        """Relu depuis la base (comme au rendu PDF/portail), releve_ids est trié
        par date — support du « justificatif chronologique » (#55/#57)."""
        periode = self.create_test_periode(self.souscription_base)
        Releve = self.env['souscription.releve']
        fin = Releve.create({'periode_id': periode.id, 'date': date(2024, 1, 31), 'index_base': 500.0})
        debut = Releve.create({'periode_id': periode.id, 'date': date(2024, 1, 1), 'index_base': 200.0})

        # Le rendu lit l'enregistrement à neuf : le _order du modèle s'applique
        # (le cache One2many garderait, lui, l'ordre de création).
        periode.invalidate_recordset(['releve_ids'])
        self.assertEqual(list(periode.releve_ids), [debut, fin])


@tagged('souscriptions', 'souscriptions_releve', 'post_install', '-at_install')
class TestReleveVerrou(SouscriptionsTestCase):
    """Verrou de facturation étendu à l'enfant (#56 / ADR 0014-0015) : dès qu'une
    Période est facturée, create / write / unlink d'un relevé sont rejetés."""

    def _periode_avec_releve(self):
        """Une Période non facturée portant un relevé."""
        periode = self.create_test_periode(self.souscription_base)
        releve = self.env['souscription.releve'].create(
            {'periode_id': periode.id, 'date': date(2024, 1, 1), 'index_base': 100.0}
        )
        return periode, releve

    def test_write_releve_periode_facturee_rejete(self):
        """write sur un relevé d'une Période facturée lève UserError."""
        periode, releve = self._periode_avec_releve()
        periode._creer_facture()  # facture_id existe → période figée

        with self.assertRaises(UserError):
            releve.index_base = 999.0

    def test_create_releve_periode_facturee_rejete(self):
        """create d'un relevé sur une Période facturée lève UserError."""
        periode, _releve = self._periode_avec_releve()
        periode._creer_facture()

        with self.assertRaises(UserError):
            self.env['souscription.releve'].create(
                {'periode_id': periode.id, 'date': date(2024, 1, 31), 'index_base': 500.0}
            )

    def test_unlink_releve_periode_facturee_rejete(self):
        """unlink d'un relevé d'une Période facturée lève UserError."""
        periode, releve = self._periode_avec_releve()
        periode._creer_facture()

        with self.assertRaises(UserError):
            releve.unlink()

    def test_releves_libres_avant_facturation(self):
        """Avant facturation : create / write / unlink restent libres."""
        periode, releve = self._periode_avec_releve()
        self.assertFalse(periode.facture_id)

        releve.index_base = 222.0  # write OK
        self.assertEqual(releve.index_base, 222.0)
        autre = self.env['souscription.releve'].create(  # create OK
            {'periode_id': periode.id, 'date': date(2024, 1, 31), 'index_base': 600.0}
        )
        autre.unlink()  # unlink OK
        self.assertFalse(autre.exists())

    def test_suppression_facture_defige_les_releves(self):
        """Supprimer la facture défige les relevés (édition de nouveau possible)."""
        periode, releve = self._periode_avec_releve()
        facture = periode._creer_facture()

        facture.unlink()  # la période et ses relevés se défigent
        self.assertFalse(periode.facture_id)

        releve.index_base = 333.0  # write de nouveau autorisé
        self.assertEqual(releve.index_base, 333.0)


@tagged('souscriptions', 'souscriptions_releve', 'post_install', '-at_install')
class TestReleveFacturePDF(SouscriptionsTestCase):
    """Bloc « Justificatif de calcul — relevés utilisés » sur la facture PDF
    (#55 / ADR 0015) : rendu par projection depuis periode_id.releve_ids, jamais
    matérialisé en account.move.line."""

    def _render_facture(self, facture):
        context = {'docs': facture, 'doc_ids': facture.ids, 'doc_model': 'account.move'}
        return str(self.env['ir.qweb']._render('souscriptions_odoo.report_facture_energie', context))

    def test_bloc_justificatif_liste_les_releves_chronologiquement(self):
        """Le bloc liste chaque relevé : date, nature étiquetée, index, par ordre de date."""
        periode = self.create_test_periode(self.souscription_base)
        Releve = self.env['souscription.releve']
        Releve.create({'periode_id': periode.id, 'date': date(2024, 1, 31), 'nature': 'estime', 'index_base': 10250.0})
        Releve.create({'periode_id': periode.id, 'date': date(2024, 1, 1), 'nature': 'reel', 'index_base': 10000.0})
        facture = periode._creer_facture()

        html = self._render_facture(facture)

        self.assertIn('relevés utilisés', html)
        self.assertIn('01/01/2024', html)
        self.assertIn('31/01/2024', html)
        self.assertIn('10000', html)
        self.assertIn('10250', html)
        self.assertIn('Réel', html)
        self.assertIn('Estimé', html)
        # Ordre chronologique : le relevé de début précède celui de fin dans le rendu.
        self.assertLess(html.index('01/01/2024'), html.index('31/01/2024'))

    def test_releves_non_materialises_en_lignes_de_facture(self):
        """Le move reste purement financier : aucune ligne ne provient des relevés."""
        periode = self.create_test_periode(self.souscription_base)
        self.env['souscription.releve'].create(
            {'periode_id': periode.id, 'date': date(2024, 1, 1), 'nature': 'reel', 'index_base': 88888.0}
        )
        facture = periode._creer_facture()

        # Base : composition = 1 ligne abonnement + 1 ligne énergie, inchangée par les relevés.
        product_lines = facture.invoice_line_ids.filtered(lambda line: line.display_type == 'product')
        self.assertEqual(len(product_lines), 2)
        self.assertNotIn('88888', ''.join(facture.invoice_line_ids.mapped('name') or []))

    def test_bloc_present_en_contrat_lisse(self):
        """En lissé, le bloc justificatif apparaît aussi (séparé des lignes facturées)."""
        self.assertTrue(self.souscription_hphc.lisse)
        self.souscription_hphc.config_cadrans = 'hp_hc'
        periode = self.create_test_periode(self.souscription_hphc)
        self.env['souscription.releve'].create(
            {
                'periode_id': periode.id,
                'date': date(2024, 1, 1),
                'nature': 'reel',
                'index_hp': 4000.0,
                'index_hc': 2000.0,
            }
        )
        facture = periode._creer_facture()

        html = self._render_facture(facture)
        self.assertIn('relevés utilisés', html)
        self.assertIn('4000', html)

    def test_changement_compteur_trois_releves_tous_listes(self):
        """≥3 relevés (changement de compteur) : tous listés, sans conso synthétique."""
        periode = self.create_test_periode(self.souscription_base)
        Releve = self.env['souscription.releve']
        Releve.create({'periode_id': periode.id, 'date': date(2024, 1, 1), 'nature': 'reel', 'index_base': 9000.0})
        Releve.create({'periode_id': periode.id, 'date': date(2024, 1, 15), 'nature': 'reel', 'index_base': 9100.0})
        Releve.create({'periode_id': periode.id, 'date': date(2024, 1, 31), 'nature': 'reel', 'index_base': 50.0})
        facture = periode._creer_facture()

        html = self._render_facture(facture)
        for jalon in ('01/01/2024', '15/01/2024', '31/01/2024'):
            self.assertIn(jalon, html)
