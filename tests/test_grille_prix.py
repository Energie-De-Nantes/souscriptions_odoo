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
