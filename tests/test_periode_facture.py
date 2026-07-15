"""
Tests du lien Période ↔ Facture (issue #23 / ADR 0004).

`account.move.periode_id` est l'unique source de vérité du lien : la période
expose sa facture via `facture_id`, champ calculé/stocké dérivé de ce lien.
"""

from datetime import date

from odoo.tests.common import tagged

from .common import SouscriptionsTestCase, build_grille_lignes


@tagged('souscriptions', 'souscriptions_periode_facture', 'post_install', '-at_install')
class TestPeriodeFactureLien(SouscriptionsTestCase):
    def test_facture_id_derive_du_periode_id(self):
        """facture_id reflète le account.move qui pointe la période via periode_id."""
        periode = self.create_test_periode(self.souscription_base)
        self.assertFalse(periode.facture_id, 'Aucune facture liée au départ')

        facture = self.env['account.move'].create(
            {
                'move_type': 'out_invoice',
                'partner_id': self.partner_test.id,
                'invoice_date': date(2024, 2, 5),
                'periode_id': periode.id,
            }
        )

        self.assertEqual(periode.facture_id, facture)

    def test_facture_ids_souscription_agrege_les_periodes(self):
        """souscription.facture_ids agrège automatiquement les factures des périodes."""
        periode = self.create_test_periode(self.souscription_base)
        facture = periode._creer_facture()
        self.assertIn(facture, self.souscription_base.facture_ids)

    def test_creer_factures_ne_double_pas(self):
        """creer_factures est idempotent : une seule facture par période (anti-doublon)."""
        self.create_test_periode(self.souscription_base, date_debut=date(2024, 1, 1), date_fin=date(2024, 1, 31))

        self.souscription_base.creer_factures()
        self.assertEqual(len(self.souscription_base.facture_ids), 1)

        # Second appel : aucune facture supplémentaire ne doit être créée.
        self.souscription_base.creer_factures()
        self.assertEqual(len(self.souscription_base.facture_ids), 1)


@tagged('souscriptions', 'souscriptions_periode_facture', 'souscriptions_cheque_energie', 'post_install', '-at_install')
class TestPeriodeFactureChequeEnergie(SouscriptionsTestCase):
    """#172, couture 2 (point de couture le plus haut) : test d'INTÉGRATION du
    câblage réel — `_creer_facture()` (brouillon) puis `action_post()`
    (`account.move._post()`) déclenchent `souscription.cheque_energie.imputer()`.
    Déplacée de la création à l'ÉMISSION par la tranche 1 du PRD #264 (#265).
    La règle elle-même (FIFO, plafond `min(solde, total)`, no-op non-validé,
    report du reliquat) est testée directement contre `imputer()` avec une
    Facture nue, sans fixture Période — cf. `test_cheque_energie.py::TestChequeEnergieImputer`
    (#255, revue d'architecture)."""

    def _new_cheque(self, **kwargs):
        vals = {
            'numero': 'CHQ-172-A',
            'partner_id': self.partner_test.id,
            'montant': 10.0,
            'date_reception': date(2024, 1, 5),
            'date_expiration': date(2025, 3, 31),
        }
        vals.update(kwargs)
        return self.env['souscription.cheque_energie'].create(vals)

    def test_imputation_declenchee_par_lemission_via_creer_facture(self):
        """AC #265 : `_creer_facture()` produit un brouillon sans imputation
        (même avec un chèque validé disponible, plus aucune facture d'énergie
        postée « en douce » à la création) ; `action_post()` délègue à
        `imputer()`, qui réduit `amount_residual` de `min(solde, total)`."""
        cheque = self._new_cheque(montant=10.0)
        cheque.action_valider()

        periode = self.create_test_periode(self.souscription_base)
        facture = periode._creer_facture()

        self.assertEqual(facture.state, 'draft')
        self.assertAlmostEqual(
            facture.amount_residual, facture.amount_total, places=2, msg='rien imputé avant émission'
        )
        self.assertAlmostEqual(cheque.solde, cheque.montant, places=2)

        facture.action_post()

        self.assertEqual(facture.state, 'posted')
        self.assertAlmostEqual(facture.amount_residual, facture.amount_total - 10.0, places=2)
        self.assertGreaterEqual(facture.amount_residual, 0.0)
        self.assertAlmostEqual(cheque.solde, 0.0, places=2)


@tagged('souscriptions', 'souscriptions_periode_facture', 'souscriptions_provenance', 'post_install', '-at_install')
class TestPeriodeFactureRegenerationEmission(SouscriptionsTestCase):
    """#266 (tranche 2 du PRD #264) : re-génération préservante à l'émission —
    `account.move._post()` recompose les lignes GÉNÉRÉES depuis la Période
    (même snapshot, même grille) et rassemble les Refacturations en file,
    tout en préservant les lignes manuelles."""

    def test_lignes_composees_par_la_periode_portent_le_flag(self):
        """Toute ligne composée par `_composer_lignes` porte
        `souscription_ligne_generee = True` (ADR 0014 amendé)."""
        periode = self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        lignes = periode._composer_lignes(self.grille_prix)
        self.assertTrue(lignes)
        self.assertTrue(all(vals.get('souscription_ligne_generee') is True for _cmd, _id, vals in lignes))

    def test_ligne_manuelle_survit_a_la_regeneration_de_l_emission(self):
        """AC #266 : une ligne manuelle ajoutée au brouillon (geste
        commercial) survit à l'émission, telle quelle."""
        periode = self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        facture = periode._creer_facture()
        produit = self.env.ref('souscriptions_odoo.souscriptions_product_energie_base')
        facture.write(
            {
                'invoice_line_ids': [
                    (0, 0, {'product_id': produit.id, 'name': 'Geste commercial', 'quantity': 1.0, 'price_unit': -5.0})
                ]
            }
        )
        ligne_manuelle = facture.invoice_line_ids.filtered(lambda l: l.name == 'Geste commercial')
        self.assertTrue(ligne_manuelle)
        self.assertFalse(ligne_manuelle.souscription_ligne_generee)

        facture.action_post()

        ligne_apres = facture.invoice_line_ids.filtered(lambda l: l.name == 'Geste commercial')
        self.assertEqual(len(ligne_apres), 1, 'la ligne manuelle survit à la re-génération')
        self.assertEqual(ligne_apres.price_unit, -5.0)

    def test_lignes_generees_recomposees_a_l_emission(self):
        """Les lignes GÉNÉRÉES sont bien re-composées (supprimées puis
        recréées) à l'émission — même structure qu'au brouillon (la provision
        et la grille ne bougent pas dans cette tranche, ADR 0030 décision 4
        vs tranche 3)."""
        periode = self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        facture = periode._creer_facture()
        ids_avant = set(facture.invoice_line_ids.filtered('souscription_ligne_generee').ids)

        facture.action_post()

        ids_apres = set(facture.invoice_line_ids.filtered('souscription_ligne_generee').ids)
        self.assertFalse(ids_avant & ids_apres, 'les anciennes lignes générées sont supprimées, pas réutilisées')
        self.assert_invoice_structure(facture)

    def test_refacturation_entree_apres_le_brouillon_rassemblee_a_l_emission(self):
        """AC #266 : une Refacturation entrée en file APRÈS la création du
        brouillon est rassemblée à l'émission (re-génération), pas seulement
        à la création."""
        periode = self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        facture = periode._creer_facture()
        self.assertFalse(facture.invoice_line_ids.filtered(lambda l: l.name == 'Déplacement tardif'))

        presta = self.env['souscription.refacturation'].create(
            {
                'souscription_id': self.souscription_base.id,
                'reference': 'F15-TARDIF',
                'libelle': 'Déplacement tardif',
                'prix': 40.0,
                'quantite': 1.0,
            }
        )
        self.assertFalse(presta.facture_id, 'encore dans la file avant émission')

        facture.action_post()

        ligne = facture.invoice_line_ids.filtered(lambda l: l.name == 'Déplacement tardif')
        self.assertEqual(len(ligne), 1)
        self.assertTrue(ligne.souscription_ligne_generee)
        self.assertEqual(presta.facture_id, facture)

    def test_refacturation_deja_rassemblee_a_la_creation_survit_a_la_regeneration(self):
        """Non-régression : une Refacturation déjà rassemblée AVANT l'émission
        (chemin de création, `souscription.creer_factures()`) n'est pas
        perdue par la re-génération — recomposée, pas seulement préservée."""
        self.env['souscription.refacturation'].create(
            {
                'souscription_id': self.souscription_base.id,
                'reference': 'F15-PRECOCE',
                'libelle': 'Déplacement précoce',
                'prix': 25.0,
                'quantite': 1.0,
            }
        )
        self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)

        self.souscription_base.creer_factures()
        facture = self.souscription_base.facture_ids
        ligne_avant = facture.invoice_line_ids.filtered(lambda l: l.name == 'Déplacement précoce')
        self.assertEqual(len(ligne_avant), 1, 'rassemblée dès la création')

        facture.action_post()

        ligne_apres = facture.invoice_line_ids.filtered(lambda l: l.name == 'Déplacement précoce')
        self.assertEqual(len(ligne_apres), 1, 'toujours présente après re-génération à l’émission')
        presta = self.souscription_base.refacturation_ids.filtered(lambda p: p.reference == 'F15-PRECOCE')
        self.assertEqual(presta.facture_id, facture)

    def test_section_prestations_enedis_non_dupliquee_a_la_regeneration(self):
        """#279 : une Refacturation déjà rassemblée à la création garde une
        section « Prestations Enedis » UNIQUE après la re-génération à
        l'émission — la recompose supprime puis recompose, pas d'empilement."""
        self.env['souscription.refacturation'].create(
            {
                'souscription_id': self.souscription_base.id,
                'reference': 'F15-SECDUP',
                'libelle': 'Déplacement',
                'prix': 25.0,
                'quantite': 1.0,
            }
        )
        self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        self.souscription_base.creer_factures()
        facture = self.souscription_base.facture_ids

        facture.action_post()

        sections = facture.invoice_line_ids.filtered(
            lambda l: l.display_type == 'line_section' and l.name == 'Prestations Enedis'
        )
        self.assertEqual(len(sections), 1, 'une seule section après re-génération')

    def test_section_prestations_enedis_disparait_quand_la_file_se_vide(self):
        """#279 : si la Refacturation quitte la file (mise en attente) avant
        une recompose, la section disparaît — elle ne survit pas comme une
        ligne orpheline."""
        presta = self.env['souscription.refacturation'].create(
            {
                'souscription_id': self.souscription_base.id,
                'reference': 'F15-SECVIDE',
                'libelle': 'Déplacement',
                'prix': 25.0,
                'quantite': 1.0,
            }
        )
        self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        self.souscription_base.creer_factures()
        facture = self.souscription_base.facture_ids
        self.assertTrue(
            facture.invoice_line_ids.filtered(
                lambda l: l.display_type == 'line_section' and l.name == 'Prestations Enedis'
            )
        )

        presta.facture_id = False
        presta.en_attente = True
        facture._recomposer_lignes_generees()

        self.assertFalse(
            facture.invoice_line_ids.filtered(
                lambda l: l.display_type == 'line_section' and l.name == 'Prestations Enedis'
            ),
            'la section disparaît quand plus aucune presta à rassembler',
        )

    def test_suppression_directe_ligne_generee_refusee_en_brouillon(self):
        """Garde `ondelete` (#266) : suppression directe d'une ligne générée
        d'une facture d'énergie en brouillon refusée."""
        periode = self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        facture = periode._creer_facture()
        ligne = facture.invoice_line_ids.filtered('souscription_ligne_generee')[:1]
        self.assertTrue(ligne)

        with self.assertRaises(Exception):
            ligne.unlink()

    def test_suppression_ligne_manuelle_autorisee(self):
        """Une ligne manuelle reste supprimable (pas de flag = pas de garde)."""
        periode = self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        facture = periode._creer_facture()
        produit = self.env.ref('souscriptions_odoo.souscriptions_product_energie_base')
        facture.write({'invoice_line_ids': [(0, 0, {'product_id': produit.id, 'name': 'Note libre', 'quantity': 1.0})]})
        ligne = facture.invoice_line_ids.filtered(lambda l: l.name == 'Note libre')
        self.assertFalse(ligne.souscription_ligne_generee)

        ligne.unlink()  # ne lève rien

        self.assertFalse(facture.invoice_line_ids.filtered(lambda l: l.name == 'Note libre'))

    def test_suppression_facture_entiere_toujours_autorisee(self):
        """La cascade (suppression du move entier) n'est jamais bloquée par
        la garde `ondelete` des lignes générées."""
        periode = self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        facture = periode._creer_facture()
        self.assertTrue(facture.invoice_line_ids.filtered('souscription_ligne_generee'))

        facture.unlink()  # ne lève rien : cascade autorisée

        self.assertFalse(periode.facture_id)


@tagged('souscriptions', 'souscriptions_periode_facture', 'souscriptions_grille_prix', 'post_install', '-at_install')
class TestPeriodeFactureSelectionGrilleSurDateDebut(SouscriptionsTestCase):
    """Sélection de la grille sur `periode.date_debut`, en lockstep sur les
    trois chemins Période (#309, ADR 0029/0032). La Période est demi-ouverte
    (`date_fin` = 1er du mois suivant) : sélectionner sur `date_fin` prixait
    un mois à la grille du mois suivant dès qu'un changement de grille
    tombait entre les deux — ce défaut n'avait jamais mordu faute d'un mois
    enjambant un changement de grille dans les fixtures existantes."""

    def test_facture_de_juin_utilise_la_grille_de_juin_pas_celle_de_juillet(self):
        """Non-régression du défaut #309 : une Période de juin, avec une
        grille B commençant le 1er juillet (même régime), se facture à la
        grille de JUIN — pas à celle que sa `date_fin` (2024-07-01) désigne."""
        grille_juillet = self.env['grille.prix'].create({'name': 'Grille Juillet 2024', 'date_debut': date(2024, 7, 1)})
        build_grille_lignes(self.env, grille_juillet, prix_base=0.99, prix_hp=0.99, prix_hc=0.99)

        periode = self.create_test_periode(
            self.souscription_base, date_debut=date(2024, 6, 1), date_fin=date(2024, 7, 1), provision_base_kwh=100.0
        )
        facture = periode._creer_facture()

        ligne = facture.invoice_line_ids.filtered(lambda l: l.name == 'Énergie Base')
        self.assertAlmostEqual(
            ligne.price_unit, 0.15, places=6, msg='grille de juin (common.py), jamais celle de juillet (0.99)'
        )

    def test_creation_et_regeneration_a_lemission_resolvent_la_meme_grille(self):
        """Lockstep (ADR 0032) : `_creer_facture` (création du brouillon) et
        `_composer_lignes_generees` (régénération à l'émission) résolvent
        la MÊME grille pour la même Période — une grille future apparue
        entre les deux ne doit rien changer, sous peine de changer
        silencieusement le prix d'une facture à son émission."""
        # La grille de juillet existe DÈS la création : c'est elle que
        # `periode.date_fin` (2024-07-01) désignerait. Sans elle, les deux
        # chemins résolvent la grille de juin même non corrigés — le test ne
        # discriminerait alors rien (#309).
        grille_juillet = self.env['grille.prix'].create({'name': 'Grille Juillet 2024', 'date_debut': date(2024, 7, 1)})
        build_grille_lignes(self.env, grille_juillet, prix_base=0.99, prix_hp=0.99, prix_hc=0.99)

        periode = self.create_test_periode(
            self.souscription_base, date_debut=date(2024, 6, 1), date_fin=date(2024, 7, 1), provision_base_kwh=100.0
        )
        facture = periode._creer_facture()
        prix_creation = facture.invoice_line_ids.filtered(lambda l: l.name == 'Énergie Base').price_unit

        # Une grille future apparaît après la création du brouillon, avant l'émission.
        grille_future = self.env['grille.prix'].create({'name': 'Grille Août 2024', 'date_debut': date(2024, 8, 1)})
        build_grille_lignes(self.env, grille_future, prix_base=0.99, prix_hp=0.99, prix_hc=0.99)

        facture.action_post()

        ligne_apres = facture.invoice_line_ids.filtered(lambda l: l.name == 'Énergie Base')
        self.assertAlmostEqual(
            ligne_apres.price_unit, prix_creation, places=6, msg='même grille à la création et à l’émission'
        )
        self.assertAlmostEqual(
            ligne_apres.price_unit, 0.15, places=6, msg='toujours la grille de juin, pas la future d’août'
        )


@tagged('souscriptions', 'souscriptions_periode_facture', 'souscriptions_provenance', 'post_install', '-at_install')
class TestPeriodeEditionBrouillonRegenerationFilDeLeau(SouscriptionsTestCase):
    """#267 (tranche 3 du PRD #264), point d'entrée (b) : éditer une Période
    NON GELÉE qui porte un brouillon de Facture recompose ce brouillon —
    AC « son édition régénère les lignes générées du brouillon (les
    manuelles restent) »."""

    def test_edition_periode_avec_brouillon_recompose_les_lignes_generees(self):
        periode = self.create_test_periode(self.souscription_hphc, provision_hp_kwh=150.0, provision_hc_kwh=100.0)
        facture = periode._creer_facture()
        hp_avant = facture.invoice_line_ids.filtered(lambda l: l.name == 'Énergie HP')
        self.assertEqual(hp_avant.quantity, 150.0)

        periode.write({'provision_hp_kwh': 175.0})  # correction du·de la facturiste

        hp_apres = facture.invoice_line_ids.filtered(lambda l: l.name == 'Énergie HP')
        self.assertEqual(hp_apres.quantity, 175.0, "l'édition régénère le brouillon")

    def test_edition_periode_avec_brouillon_preserve_la_ligne_manuelle(self):
        """La régénération au fil de l'eau reste PRÉSERVANTE (#266) : une
        ligne manuelle (geste commercial) survit à l'édition de la Période."""
        periode = self.create_test_periode(self.souscription_hphc, provision_hp_kwh=150.0, provision_hc_kwh=100.0)
        facture = periode._creer_facture()
        produit = self.env.ref('souscriptions_odoo.souscriptions_product_energie_hp')
        facture.write(
            {
                'invoice_line_ids': [
                    (0, 0, {'product_id': produit.id, 'name': 'Geste commercial', 'quantity': 1.0, 'price_unit': -5.0})
                ]
            }
        )

        periode.write({'provision_hp_kwh': 175.0})

        ligne_manuelle = facture.invoice_line_ids.filtered(lambda l: l.name == 'Geste commercial')
        self.assertEqual(len(ligne_manuelle), 1, 'la ligne manuelle survit à la régénération au fil de l’eau')
        self.assertEqual(ligne_manuelle.price_unit, -5.0)

    def test_edition_du_mesure_non_lisse_recompose_le_brouillon(self):
        """Suivi de review #271 : le mesuré est exempt du verrou (vivant, ADR
        0030) et un non-lissé non tamponné le facture en direct — sa saisie
        manuelle (« estimations quand le flux Enedis manque », CONTEXT.md)
        doit se refléter en live dans le brouillon, comme une provision."""
        periode = self.create_test_periode(self.souscription_base, energie_base_kwh=100.0)
        self.assertFalse(periode.lisse_periode)
        facture = periode._creer_facture()
        ligne = facture.invoice_line_ids.filtered(lambda l: l.name == 'Énergie Base')
        self.assertEqual(ligne.quantity, 100.0)

        periode.write({'energie_base_kwh': 130.0})  # estimation corrigée à la main

        ligne = facture.invoice_line_ids.filtered(lambda l: l.name == 'Énergie Base')
        self.assertEqual(ligne.quantity, 130.0, 'le mesuré corrigé se reflète en live dans le brouillon')

    def test_edition_periode_sans_brouillon_ne_leve_rien(self):
        """Non-régression : éditer une Période sans aucune Facture liée reste
        un no-op côté régénération (rien à recomposer)."""
        periode = self.create_test_periode(self.souscription_base, provision_base_kwh=100.0)
        self.assertFalse(periode.facture_id)

        periode.write({'provision_base_kwh': 150.0})  # ne lève rien

        self.assertEqual(periode.provision_base_kwh, 150.0)
