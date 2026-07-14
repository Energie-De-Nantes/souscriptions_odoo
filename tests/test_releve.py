"""
Relevés d'index (#54 / ADR 0015) : modèle enfant `souscription.releve` de la
Période, saisie backend. Forme large par cadran réseau, nature réel/estimé,
cardinalité variable. Pas de verrou ici (#56) ni de rendu (#55/#57).
"""

import os
import runpy
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

    def test_index_sont_des_champs_integer(self):
        """Les 7 index (#132) sont des `fields.Integer` — un index de compteur
        electricore est un entier kWh par construction (ADR-0034 côté
        electricore), affiché sans décimale ni widget côté Odoo."""
        Releve = self.env['souscription.releve']
        champs_index = (
            'index_hph',
            'index_hpb',
            'index_hch',
            'index_hcb',
            'index_hp',
            'index_hc',
            'index_base',
        )
        for champ in champs_index:
            self.assertEqual(Releve._fields[champ].type, 'integer', champ)

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
class TestReleveColonnesUnionFamilles(SouscriptionsTestCase):
    """`releve_colonnes()` = union des familles de cadrans réellement relevées
    (#138, amende ADR 0015) — plus une lecture directe de `config_cadrans`."""

    def test_une_seule_famille_ignore_config_cadrans_declare(self):
        """Période déclarée hp_hc dont l'unique relevé porte les 4 cadrans
        (compteur remplacé) : seules les colonnes 4 cadrans apparaissent —
        aucune colonne HP/HC parasite à zéro."""
        self.souscription_hphc.config_cadrans = 'hp_hc'
        periode = self.create_test_periode(self.souscription_hphc)
        self.env['souscription.releve'].create(
            {
                'periode_id': periode.id,
                'date': date(2024, 1, 1),
                'nature': 'reel',
                'index_hph': 1000,
                'index_hpb': 2000,
                'index_hch': 3000,
                'index_hcb': 4000,
            }
        )

        self.assertEqual(
            [c['field'] for c in periode.releve_colonnes()],
            ['index_hph', 'index_hpb', 'index_hch', 'index_hcb'],
        )

    def test_deux_familles_union_ordonnee_superficiel_a_profond(self):
        """Changement de compteur HP/HC → 4 cadrans en cours de période : union
        ordonnée [HP, HC, HPH, HPB, HCH, HCB], chaque relevé ne remplissant que
        les registres de son propre compteur (diff visuel de la transition)."""
        self.souscription_hphc.config_cadrans = 'hp_hc'
        periode = self.create_test_periode(self.souscription_hphc)
        Releve = self.env['souscription.releve']
        Releve.create(
            {'periode_id': periode.id, 'date': date(2024, 1, 1), 'nature': 'reel', 'index_hp': 8000, 'index_hc': 4000}
        )
        Releve.create(
            {
                'periode_id': periode.id,
                'date': date(2024, 1, 31),
                'nature': 'reel',
                'index_hph': 10,
                'index_hpb': 20,
                'index_hch': 30,
                'index_hcb': 40,
            }
        )

        self.assertEqual(
            [c['field'] for c in periode.releve_colonnes()],
            ['index_hp', 'index_hc', 'index_hph', 'index_hpb', 'index_hch', 'index_hcb'],
        )

    def test_aucun_relevé_replie_sur_config_cadrans_declare(self):
        """Aucun relevé du tout : repli sur le config_cadrans déclaré — la
        saisie manuelle (#12) garde des colonnes où écrire."""
        self.souscription_hphc.config_cadrans = 'hp_hc'
        periode = self.create_test_periode(self.souscription_hphc)
        self.assertFalse(periode.releve_ids)

        self.assertEqual([c['field'] for c in periode.releve_colonnes()], ['index_hp', 'index_hc'])

    def test_releves_sans_aucun_index_replie_sur_config_cadrans_declare(self):
        """Des relevés existent mais aucun n'a d'index renseigné (tous à 0) :
        même repli sur config_cadrans que l'absence totale de relevé."""
        self.souscription_hphc.config_cadrans = '4_cadrans'
        periode = self.create_test_periode(self.souscription_hphc)
        self.env['souscription.releve'].create({'periode_id': periode.id, 'date': date(2024, 1, 1), 'nature': 'estime'})

        self.assertEqual(
            [c['field'] for c in periode.releve_colonnes()],
            ['index_hph', 'index_hpb', 'index_hch', 'index_hcb'],
        )

    def test_booleens_releve_show_gatent_le_formulaire_backend(self):
        """`releve_show_base/hphc/4cadrans` (gating XML, `column_invisible` ne
        pouvant appeler une méthode) reflètent l'union — plusieurs peuvent être
        vrais simultanément, impossible à représenter par une Selection."""
        self.souscription_hphc.config_cadrans = 'hp_hc'
        periode = self.create_test_periode(self.souscription_hphc)
        Releve = self.env['souscription.releve']
        Releve.create(
            {'periode_id': periode.id, 'date': date(2024, 1, 1), 'nature': 'reel', 'index_hp': 100, 'index_hc': 50}
        )
        Releve.create(
            {
                'periode_id': periode.id,
                'date': date(2024, 1, 31),
                'nature': 'reel',
                'index_hph': 10,
                'index_hpb': 20,
                'index_hch': 30,
                'index_hcb': 40,
            }
        )

        self.assertFalse(periode.releve_show_base)
        self.assertTrue(periode.releve_show_hphc)
        self.assertTrue(periode.releve_show_4cadrans)


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

    def test_write_releve_periode_facture_emise_rejete(self):
        """write sur un relevé d'une Période dont la Facture est ÉMISE
        (postée) lève UserError (#14, condition dérivée amendée #267)."""
        periode, releve = self._periode_avec_releve()
        periode._creer_facture().action_post()  # facture émise → période figée

        with self.assertRaises(UserError):
            releve.index_base = 999.0

    def test_create_releve_periode_facture_emise_rejete(self):
        """create d'un relevé sur une Période dont la Facture est ÉMISE lève
        UserError."""
        periode, _releve = self._periode_avec_releve()
        periode._creer_facture().action_post()

        with self.assertRaises(UserError):
            self.env['souscription.releve'].create(
                {'periode_id': periode.id, 'date': date(2024, 1, 31), 'index_base': 500.0}
            )

    def test_unlink_releve_periode_facture_emise_rejete(self):
        """unlink d'un relevé d'une Période dont la Facture est ÉMISE lève
        UserError."""
        periode, releve = self._periode_avec_releve()
        periode._creer_facture().action_post()

        with self.assertRaises(UserError):
            releve.unlink()

    def test_releves_libres_avant_facturation(self):
        """Avant toute facture : create / write / unlink restent libres."""
        periode, releve = self._periode_avec_releve()
        self.assertFalse(periode.facture_id)

        releve.index_base = 222.0  # write OK
        self.assertEqual(releve.index_base, 222.0)
        autre = self.env['souscription.releve'].create(  # create OK
            {'periode_id': periode.id, 'date': date(2024, 1, 31), 'index_base': 600.0}
        )
        autre.unlink()  # unlink OK
        self.assertFalse(autre.exists())

    def test_releves_libres_avec_facture_brouillon(self):
        """AC #267 : une Facture en BROUILLON qui référence la Période ne fige
        pas ses relevés — write / create / unlink restent libres tant que la
        facture n'est pas émise. Preuve, sans migration de données, que les
        relevés gelés sous l'ancien régime (facture_id truthy = gelé) avec
        facture encore en brouillon sont DE FAIT dé-gelés par la condition
        dérivée."""
        periode, releve = self._periode_avec_releve()
        facture = periode._creer_facture()
        self.assertEqual(facture.state, 'draft')

        releve.index_base = 777.0  # ne lève rien
        self.assertEqual(releve.index_base, 777.0)
        autre = self.env['souscription.releve'].create(
            {'periode_id': periode.id, 'date': date(2024, 1, 31), 'index_base': 800.0}
        )
        autre.unlink()  # ne lève rien
        self.assertFalse(autre.exists())

    def test_remise_en_brouillon_reouvre_lecriture_des_releves(self):
        """Non-régression, seul le déclencheur change (#267) : le verrou est
        symétrique de l'état réel de la Facture — remettre en brouillon une
        Facture émise (`button_draft`) rouvre l'écriture des relevés, sans
        suppression ni « défigeage » explicite."""
        periode, releve = self._periode_avec_releve()
        facture = periode._creer_facture()
        facture.action_post()
        with self.assertRaises(UserError):
            releve.index_base = 999.0

        facture.button_draft()

        releve.index_base = 333.0  # de nouveau autorisé
        self.assertEqual(releve.index_base, 333.0)


@tagged('souscriptions', 'souscriptions_releve', 'post_install', '-at_install')
class TestReleveFacturePDF(SouscriptionsTestCase):
    """Bloc « Justificatif de calcul — relevés utilisés » sur la facture PDF
    (#55 / ADR 0015) : rendu par projection depuis periode_id.releve_ids, jamais
    matérialisé en account.move.line."""

    def _render_facture(self, facture):
        # Vrai chemin (#289) : account.account_invoices est l'action Imprimer
        # par défaut — report_facture_energie n'est plus qu'un document que
        # account.report_invoice appelle, il n'a plus de contexte de rendu
        # autonome (docs/doc_ids/doc_model).
        html_bytes, _dummy = self.env['ir.actions.report']._render_qweb_html('account.account_invoices', facture.ids)
        return html_bytes.decode()

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
        # Integer (#132) : entier sans partie décimale, sans passer par '%g'.
        self.assertNotIn('10000.0', html)
        self.assertNotIn('10250.0', html)
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

    def test_swap_compteur_deux_familles_affiche_union_sur_le_pdf(self):
        """Facturée Base mais relevée par deux familles (swap de compteur en
        cours de période, #138) : le PDF affiche l'union des colonnes — Base ET
        HPH/HPB/HCH/HCB — pas seulement Base comme le ferait config_cadrans lu
        directement. Même source (releve_colonnes()) que le portail et le
        formulaire backend."""
        periode = self.create_test_periode(self.souscription_base)
        self.assertEqual(periode.config_cadrans, 'base')
        Releve = self.env['souscription.releve']
        Releve.create({'periode_id': periode.id, 'date': date(2024, 1, 1), 'nature': 'reel', 'index_base': 88801})
        Releve.create(
            {
                'periode_id': periode.id,
                'date': date(2024, 1, 31),
                'nature': 'reel',
                'index_hph': 711,
                'index_hpb': 622,
                'index_hch': 533,
                'index_hcb': 444,
            }
        )
        facture = periode._creer_facture()

        html = self._render_facture(facture)
        # Les deux familles sont rendues : la valeur d'index_base (relevé avant
        # swap) ET les 4 index HPH/HPB/HCH/HCB (relevé après swap) apparaissent
        # — l'ancienne lecture directe de config_cadrans n'aurait affiché que
        # la colonne Base, jamais ces 4 valeurs.
        self.assertIn('88801', html)
        for valeur in ('711', '622', '533', '444'):
            self.assertIn(valeur, html)


@tagged('souscriptions', 'souscriptions_releve', 'post_install', '-at_install')
class TestMigrationIndexInteger(SouscriptionsTestCase):
    """Migration `19.0.1.7.0/pre-migrate.py` (#132) : conversion double
    precision -> integer des 7 colonnes index_*. Testée sans base réelle via
    la fonction pure `_colonnes_a_convertir`, chargée par chemin (le dossier
    de version n'est pas un identifiant Python importable)."""

    @staticmethod
    def _migration():
        chemin = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'migrations', '19.0.1.7.0', 'pre-migrate.py')
        return runpy.run_path(chemin)

    def test_colonnes_double_precision_toutes_a_convertir(self):
        migration = self._migration()
        types_avant = dict.fromkeys(migration['COLONNES_INDEX'], 'double precision')
        self.assertEqual(
            sorted(migration['_colonnes_a_convertir'](types_avant)),
            sorted(migration['COLONNES_INDEX']),
        )

    def test_colonnes_deja_integer_ignorees_idempotence(self):
        """Upgrade rejoué (déjà migré) : aucune colonne à reconvertir."""
        migration = self._migration()
        types_deja_migres = dict.fromkeys(migration['COLONNES_INDEX'], 'integer')
        self.assertEqual(migration['_colonnes_a_convertir'](types_deja_migres), [])

    def test_colonne_absente_ignoree(self):
        """Colonne absente du dict (table pas encore créée) : ignorée."""
        migration = self._migration()
        self.assertEqual(migration['_colonnes_a_convertir']({}), [])
