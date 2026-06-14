from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged

from .common import ABO_ANNUEL_SOL, ABO_ANNUEL_STD, build_grille_lignes


@tagged('souscriptions', 'post_install', '-at_install')
class TestGrillePrix(TransactionCase):
    def setUp(self):
        super().setUp()
        # Neutraliser le drapeau is_current des grilles existantes (démo)
        self.env['grille.prix'].search([('is_current', '=', True)]).write({'is_current': False})

        self.grille = self.env['grille.prix'].create(
            {
                'name': 'Grille Test 2024',
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 12, 31),
                'active': True,
                'is_current': True,
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
        """9 abonnements standard + 9 solidaires + 3 énergies = 21 lignes."""
        self.assertEqual(self.grille.name, 'Grille Test 2024')
        self.assertTrue(self.grille.active)
        self.assertEqual(len(self.grille.ligne_ids), 21)

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

    def test_calcul_prix_abonnement_particulier(self):
        """Prix journalier = prix annuel de la puissance / 365."""
        prix_journalier = self.grille.get_prix_abonnement(puissance_kva=6.0, coeff_pro=0.0, is_solidaire=False)
        self.assertAlmostEqual(prix_journalier, ABO_ANNUEL_STD['6'] / 365.0, places=4)

    def test_calcul_prix_abonnement_pro(self):
        """La majoration PRO s'applique au prix journalier."""
        prix_journalier = self.grille.get_prix_abonnement(puissance_kva=9.0, coeff_pro=15.0, is_solidaire=False)
        attendu = (ABO_ANNUEL_STD['9'] / 365.0) * 1.15
        self.assertAlmostEqual(prix_journalier, attendu, places=4)

    def test_calcul_prix_abonnement_solidaire(self):
        """Le tarif solidaire utilise sa propre grille de prix."""
        prix_journalier = self.grille.get_prix_abonnement(puissance_kva=3.0, coeff_pro=0.0, is_solidaire=True)
        self.assertAlmostEqual(prix_journalier, ABO_ANNUEL_SOL['3'] / 365.0, places=4)

    def test_prix_independant_par_puissance(self):
        """Chaque puissance a un prix indépendant, pas une formule linéaire."""
        prix_6 = self.grille.get_prix_abonnement(6.0)
        prix_9 = self.grille.get_prix_abonnement(9.0)
        # Les deux prix viennent de la grille, pas d'un facteur kVA/3
        self.assertAlmostEqual(prix_6, ABO_ANNUEL_STD['6'] / 365.0, places=4)
        self.assertAlmostEqual(prix_9, ABO_ANNUEL_STD['9'] / 365.0, places=4)
        self.assertNotAlmostEqual(prix_9, prix_6 * (9.0 / 6.0), places=4)

    def test_puissance_sans_tarif(self):
        """Une puissance absente de la grille lève une erreur claire."""
        # Supprimer la ligne 36 kVA standard
        self.grille.ligne_ids.filtered(
            lambda l: (
                l.type_produit == 'abonnement' and l.puissance == '36' and 'solidaire' not in l.product_id.name.lower()
            )
        ).unlink()
        with self.assertRaises(UserError):
            self.grille.get_prix_abonnement(36.0, is_solidaire=False)

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

    def test_abonnement_sans_puissance_interdit(self):
        """Une ligne d'abonnement sans puissance est refusée."""
        produit = self.env.ref('souscriptions_odoo.souscriptions_product_abonnement_standard')
        with self.assertRaises(ValidationError):
            self.env['grille.prix.ligne'].create(
                {
                    'grille_id': self.grille.id,
                    'product_id': produit.id,
                    'type_produit': 'abonnement',
                    'prix_abonnement_annuel': 100.0,
                }
            )
