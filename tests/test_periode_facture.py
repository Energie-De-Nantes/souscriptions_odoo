"""
Tests du lien Période ↔ Facture (issue #23 / ADR 0004).

`account.move.periode_id` est l'unique source de vérité du lien : la période
expose sa facture via `facture_id`, champ calculé/stocké dérivé de ce lien.
"""

from datetime import date

from odoo.tests.common import tagged

from .common import SouscriptionsTestCase


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
    """#172, couture 2 (point de couture le plus haut) : effet de l'imputation
    FIFO des chèques énergie validés sur `amount_residual`. Déplacée de la
    création à l'ÉMISSION par la tranche 1 du PRD #264 (#265) : `_creer_facture()`
    ne produit plus qu'un brouillon, l'imputation ne se déclenche qu'à
    `action_post()` (via `account.move._post()`, ADR 0026)."""

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

    def test_creation_avec_cheque_valide_reste_en_brouillon(self):
        """AC #265 : même avec un chèque validé à solde positif disponible,
        la création de la facture ne poste plus rien — plus aucune facture
        d'énergie postée à la création, par aucun chemin."""
        cheque = self._new_cheque(montant=10.0)
        cheque.action_valider()

        periode = self.create_test_periode(self.souscription_base)
        facture = periode._creer_facture()

        self.assertEqual(facture.state, 'draft')
        self.assertAlmostEqual(facture.amount_residual, facture.amount_total, places=2)
        self.assertAlmostEqual(cheque.solde, cheque.montant, places=2, msg='rien imputé avant émission')

    def test_cheque_valide_reduit_amount_residual_sans_jamais_etre_negatif(self):
        """Facture couverte partiellement par un chèque validé : à l'émission,
        amount_residual réduit de min(solde, total), jamais négatif."""
        cheque = self._new_cheque(montant=10.0)
        cheque.action_valider()

        periode = self.create_test_periode(self.souscription_base)
        facture = periode._creer_facture()
        facture.action_post()

        self.assertEqual(facture.state, 'posted')
        self.assertAlmostEqual(facture.amount_residual, facture.amount_total - 10.0, places=2)
        self.assertGreaterEqual(facture.amount_residual, 0.0)
        self.assertAlmostEqual(cheque.solde, 0.0, places=2)

    def test_cheque_non_valide_aucun_effet(self):
        """Un chèque 'reçu' (non validé) n'impute rien, même à l'émission :
        amount_residual == amount_total, comme sans chèque du tout
        (non-régression, AC #265)."""
        self._new_cheque(montant=1000.0)  # jamais validé

        periode = self.create_test_periode(self.souscription_base)
        facture = periode._creer_facture()
        self.assertEqual(facture.state, 'draft')

        facture.action_post()

        self.assertEqual(facture.state, 'posted')
        self.assertAlmostEqual(facture.amount_residual, facture.amount_total, places=2)

    def test_fifo_par_expiration_le_plus_proche_consomme_en_premier(self):
        """Deux chèques validés : à l'émission, celui qui périme le plus tôt
        est consommé en premier (FIFO par expiration), quel que soit l'ordre
        de création/montant."""
        cheque_tardif = self._new_cheque(numero='CHQ-172-TARD', montant=1000.0, date_expiration=date(2026, 3, 31))
        cheque_tardif.action_valider()
        cheque_proche = self._new_cheque(numero='CHQ-172-PROCHE', montant=5.0, date_expiration=date(2024, 3, 31))
        cheque_proche.action_valider()

        periode = self.create_test_periode(self.souscription_base)
        facture = periode._creer_facture()
        facture.action_post()

        # Le chèque qui périme le plus tôt (proche) est épuisé en premier ;
        # le tardif n'absorbe que ce que le proche n'a pas couvert.
        self.assertAlmostEqual(cheque_proche.solde, 0.0, places=2)
        self.assertAlmostEqual(
            cheque_tardif.solde,
            cheque_tardif.montant - (facture.amount_total - cheque_proche.montant),
            places=2,
        )
        self.assertAlmostEqual(facture.amount_residual, 0.0, places=2)

    def test_reliquat_se_reporte_sur_la_facture_suivante(self):
        """Un chèque plus gros qu'une Facture se reporte sur la Facture suivante
        jusqu'à épuisement — report natif du lettrage, pas de code métier.
        Chaque Facture est émise (`action_post()`) pour déclencher l'imputation."""
        cheque = self._new_cheque(montant=1000.0)
        cheque.action_valider()

        periode_janvier = self.create_test_periode(
            self.souscription_base, date_debut=date(2024, 1, 1), date_fin=date(2024, 1, 31)
        )
        facture_janvier = periode_janvier._creer_facture()
        facture_janvier.action_post()
        self.assertAlmostEqual(facture_janvier.amount_residual, 0.0, places=2)
        solde_apres_janvier = cheque.solde
        self.assertGreater(solde_apres_janvier, 0.0)

        periode_fevrier = self.create_test_periode(
            self.souscription_base, date_debut=date(2024, 2, 1), date_fin=date(2024, 2, 29)
        )
        facture_fevrier = periode_fevrier._creer_facture()
        facture_fevrier.action_post()

        self.assertAlmostEqual(facture_fevrier.amount_residual, 0.0, places=2)
        self.assertAlmostEqual(cheque.solde, solde_apres_janvier - facture_fevrier.amount_total, places=2)

    def test_structure_facture_et_pas_de_ligne_negative(self):
        """Tiers-payeur, jamais une remise (ADR 0026) : la structure de la
        Facture (sections, notes TURPE, lignes produit) et son CA/TVA ne sont
        pas touchés par l'imputation à l'émission — aucune ligne négative
        n'est ajoutée."""
        cheque = self._new_cheque(montant=10.0)
        cheque.action_valider()

        periode = self.create_test_periode(self.souscription_base)
        facture = periode._creer_facture()
        facture.action_post()

        self.assert_invoice_structure(facture)
        lignes_produit = facture.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
        self.assertTrue(lignes_produit)
        self.assertTrue(all(l.quantity >= 0 and l.price_unit >= 0 for l in lignes_produit))
        self.assertAlmostEqual(facture.amount_untaxed, sum(lignes_produit.mapped('price_subtotal')), places=2)


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
