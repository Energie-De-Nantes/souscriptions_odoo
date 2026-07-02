from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import mute_logger
from psycopg2 import IntegrityError

from .common import (
    ABO_BASE_3KVA_SOL,
    ABO_BASE_3KVA_STD,
    ABO_COEF_KVA_SOL,
    ABO_COEF_KVA_STD,
    build_grille_lignes,
)


@tagged('souscriptions', 'post_install', '-at_install')
class TestGrillePrix(TransactionCase):
    def setUp(self):
        super().setUp()
        self.grille = self.env['grille.prix'].create(
            {
                'name': 'Grille Test 2024',
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 12, 31),
                'active': True,
            }
        )
        build_grille_lignes(
            self.env,
            self.grille,
            prix_base=0.2276,
            prix_hp=0.2516,
            prix_hc=0.2032,
        )

    def test_grille_creation(self):
        """2 abo affine (std + sol) + 3 énergies std + 3 énergies solidaires = 8 lignes (ADR 0018)."""
        self.assertEqual(self.grille.name, 'Grille Test 2024')
        self.assertTrue(self.grille.active)
        self.assertEqual(len(self.grille.ligne_ids), 8)

    def test_get_grille_active_par_date(self):
        """La grille est sélectionnée selon la date, pas le drapeau is_current."""
        grille_active = self.env['grille.prix'].get_grille_active(date(2024, 6, 15))
        self.assertEqual(grille_active, self.grille)

    def test_get_grille_active_trou_de_periode(self):
        """Une date non couverte par aucune grille lève une erreur."""
        with self.assertRaises(UserError):
            self.env['grille.prix'].get_grille_active(date(2023, 1, 1))

    def test_selection_grille_historique(self):
        """Facturer une période passée utilise la grille de cette période."""
        grille_2023 = self.env['grille.prix'].create(
            {
                'name': 'Grille 2023',
                'date_debut': date(2023, 1, 1),
                'date_fin': date(2023, 12, 31),
            }
        )
        build_grille_lignes(
            self.env,
            grille_2023,
            prix_base=0.10,
            prix_hp=0.10,
            prix_hc=0.10,
        )
        self.assertEqual(
            self.env['grille.prix'].get_grille_active(date(2023, 5, 1)),
            grille_2023,
        )
        self.assertEqual(
            self.env['grille.prix'].get_grille_active(date(2024, 5, 1)),
            self.grille,
        )

    def test_get_prix_dict(self):
        prix_dict = self.grille.get_prix_dict()
        produit_base = self.env.ref('souscriptions_odoo.souscriptions_product_energie_base')
        produit_hp = self.env.ref('souscriptions_odoo.souscriptions_product_energie_hp')
        produit_hc = self.env.ref('souscriptions_odoo.souscriptions_product_energie_hc')
        self.assertEqual(prix_dict[produit_base.id], 0.2276)
        self.assertEqual(prix_dict[produit_hp.id], 0.2516)
        self.assertEqual(prix_dict[produit_hc.id], 0.2032)

    def test_abonnement_affine_a_3kva(self):
        """À 3 kVA, le tarif vaut exactement la base (terme coef nul)."""
        prix_journalier = self.grille.get_prix_abonnement(puissance_kva=3.0, coeff_pro=0.0, is_solidaire=False)
        self.assertAlmostEqual(prix_journalier, ABO_BASE_3KVA_STD / 365.0, places=4)

    def test_abonnement_affine_puissance_non_3kva(self):
        """Au-dessus de 3 kVA : base + coef * (P - 3), proratisé au jour."""
        prix_journalier = self.grille.get_prix_abonnement(puissance_kva=9.0, coeff_pro=0.0, is_solidaire=False)
        attendu_annuel = ABO_BASE_3KVA_STD + ABO_COEF_KVA_STD * (9.0 - 3.0)
        self.assertAlmostEqual(prix_journalier, attendu_annuel / 365.0, places=4)

    def test_abonnement_affine_lineaire_dans_la_puissance(self):
        """L'écart entre deux puissances vaut coef * Δkva / 365 (forme affine)."""
        prix_6 = self.grille.get_prix_abonnement(6.0)
        prix_9 = self.grille.get_prix_abonnement(9.0)
        self.assertAlmostEqual(prix_9 - prix_6, ABO_COEF_KVA_STD * 3.0 / 365.0, places=6)

    def test_abonnement_affine_pro(self):
        """La majoration PRO s'applique au tarif affine journalier."""
        prix_journalier = self.grille.get_prix_abonnement(puissance_kva=9.0, coeff_pro=15.0, is_solidaire=False)
        attendu_annuel = ABO_BASE_3KVA_STD + ABO_COEF_KVA_STD * (9.0 - 3.0)
        self.assertAlmostEqual(prix_journalier, (attendu_annuel / 365.0) * 1.15, places=4)

    def test_abonnement_affine_solidaire(self):
        """Le solidaire lit sa propre ligne (base + coef) via le produit du catalogue."""
        prix_journalier = self.grille.get_prix_abonnement(puissance_kva=12.0, coeff_pro=0.0, is_solidaire=True)
        attendu_annuel = ABO_BASE_3KVA_SOL + ABO_COEF_KVA_SOL * (12.0 - 3.0)
        self.assertAlmostEqual(prix_journalier, attendu_annuel / 365.0, places=4)

    def test_abonnement_sans_ligne(self):
        """Sans ligne d'abonnement pour l'univers, l'erreur est claire."""
        self.grille.ligne_ids.filtered(
            lambda l: l.type_produit == 'abonnement' and 'solidaire' not in l.product_id.name.lower()
        ).unlink()
        with self.assertRaises(UserError):
            self.grille.get_prix_abonnement(6.0, is_solidaire=False)

    def test_chevauchement_grilles_interdit(self):
        """Deux grilles aux périodes qui se chevauchent sont refusées."""
        with self.assertRaises(ValidationError):
            self.env['grille.prix'].create(
                {
                    'name': 'Grille 2024 Bis',
                    'date_debut': date(2024, 6, 1),
                    'date_fin': date(2024, 12, 31),
                }
            )

    def test_produit_unique_par_grille(self):
        """Un même produit ne peut apparaître qu'une fois par grille (plus de palier)."""
        produit = self.env.ref('souscriptions_odoo.souscriptions_product_abonnement_standard')
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.env['grille.prix.ligne'].create(
                {
                    'grille_id': self.grille.id,
                    'product_id': produit.id,
                    'type_produit': 'abonnement',
                    'prix_base_3kva': 100.0,
                    'coef_kva': 5.0,
                }
            )
            self.env.flush_all()

    # === Régime de prix (standard | Moulin) — #105 ===

    def test_regime_prix_defaut_standard(self):
        """Une grille sans régime précisé est standard par défaut."""
        self.assertEqual(self.grille.regime_prix, 'standard')

    def test_grilles_moulin_et_standard_coexistent(self):
        """Deux grilles ouvertes de régimes différents, mêmes dates, coexistent :
        l'anti-chevauchement joue par régime (CONTEXT.md « Régime de prix »)."""
        grille_moulin = self.env['grille.prix'].create(
            {
                'name': 'Grille Moulin 2024',
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 12, 31),
                'regime_prix': 'moulin',
            }
        )
        self.assertEqual(grille_moulin.regime_prix, 'moulin')
        # La grille standard n'a pas été affectée par la création de la Moulin.
        self.assertEqual(self.grille.date_fin, date(2024, 12, 31))

    def test_chevauchement_meme_regime_toujours_interdit(self):
        """Deux grilles Moulin qui se chevauchent restent interdites (l'anti-
        chevauchement joue toujours au sein d'un même régime)."""
        self.env['grille.prix'].create(
            {
                'name': 'Grille Moulin A',
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 6, 30),
                'regime_prix': 'moulin',
            }
        )
        with self.assertRaises(ValidationError):
            self.env['grille.prix'].create(
                {
                    'name': 'Grille Moulin B',
                    'date_debut': date(2024, 6, 1),
                    'date_fin': date(2024, 12, 31),
                    'regime_prix': 'moulin',
                }
            )

    def test_fermeture_automatique_scopee_par_regime(self):
        """La création d'une grille ne ferme que la grille OUVERTE précédente du
        même régime — jamais une grille ouverte d'un autre régime."""
        standard_ouverte = self.env['grille.prix'].create(
            {
                'name': 'Standard 2025',
                'date_debut': date(2025, 1, 1),
            }
        )
        moulin_1 = self.env['grille.prix'].create(
            {
                'name': 'Moulin 2025',
                'date_debut': date(2025, 1, 1),
                'regime_prix': 'moulin',
            }
        )
        # La grille standard ouverte n'est pas fermée par la création de la Moulin.
        self.assertFalse(standard_ouverte.date_fin)

        self.env['grille.prix'].create(
            {
                'name': 'Moulin 2025 bis',
                'date_debut': date(2025, 6, 1),
                'regime_prix': 'moulin',
            }
        )
        # Seule la grille Moulin précédente est fermée.
        self.assertEqual(moulin_1.date_fin, date(2025, 5, 31))
        self.assertFalse(standard_ouverte.date_fin)

    def test_get_grille_active_par_regime(self):
        """La sélection se fait par (régime, date) : standard et Moulin sont
        résolus indépendamment, même sur des dates identiques."""
        grille_moulin = self.env['grille.prix'].create(
            {
                'name': 'Grille Moulin 2024',
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 12, 31),
                'regime_prix': 'moulin',
            }
        )
        self.assertEqual(
            self.env['grille.prix'].get_grille_active(date(2024, 6, 15), regime='standard'),
            self.grille,
        )
        self.assertEqual(
            self.env['grille.prix'].get_grille_active(date(2024, 6, 15), regime='moulin'),
            grille_moulin,
        )

    def test_get_grille_active_defaut_standard(self):
        """Sans régime précisé, get_grille_active reste sur le standard (compat)."""
        self.assertEqual(self.env['grille.prix'].get_grille_active(date(2024, 6, 15)), self.grille)

    def test_get_grille_active_moulin_sans_grille_leve(self):
        """Un trou de couverture Moulin lève, même si le standard couvre la date :
        les deux régimes ne se substituent jamais l'un à l'autre."""
        with self.assertRaises(UserError):
            self.env['grille.prix'].get_grille_active(date(2024, 6, 15), regime='moulin')

    def test_dupliquer_grille_conserve_le_regime(self):
        """Dupliquer une grille Moulin produit une nouvelle grille Moulin."""
        grille_moulin = self.env['grille.prix'].create(
            {
                'name': 'Grille Moulin 2023',
                'date_debut': date(2023, 1, 1),
                'date_fin': date(2023, 12, 31),
                'regime_prix': 'moulin',
            }
        )
        action = grille_moulin.dupliquer_cette_grille()
        nouvelle = self.env['grille.prix'].browse(action['res_id'])
        self.assertEqual(nouvelle.regime_prix, 'moulin')
