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
        # date_fin est dérivée (#309) : jamais saisie à la création — cette
        # grille reste ouverte tant qu'aucune grille standard plus récente
        # n'existe.
        self.grille = self.env['grille.prix'].create(
            {
                'name': 'Grille Test 2024',
                'date_debut': date(2024, 1, 1),
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

    def test_get_grille_active_selectionne_la_plus_recente_a_avoir_commence(self):
        """« La grille en vigueur est la plus récente à avoir commencé » : une
        date qui tombe APRÈS le début de deux grilles du même régime résout
        toujours sur celle dont le début est le plus proche (le plus grand,
        toujours <= la date), jamais sur une notion de fin stockée."""
        grille_2025 = self.env['grille.prix'].create({'name': 'Grille 2025', 'date_debut': date(2025, 1, 1)})
        build_grille_lignes(self.env, grille_2025, prix_base=0.30, prix_hp=0.30, prix_hc=0.30)

        self.assertEqual(self.env['grille.prix'].get_grille_active(date(2024, 12, 31)), self.grille)
        self.assertEqual(self.env['grille.prix'].get_grille_active(date(2025, 1, 1)), grille_2025)
        self.assertEqual(self.env['grille.prix'].get_grille_active(date(2030, 1, 1)), grille_2025)

    # === date_fin dérivée (#309) : plus stockée, plus fermée par create() ===

    def test_date_fin_vide_quand_aucune_grille_suivante(self):
        """Sans grille plus récente du même régime, date_fin reste vide (grille
        encore ouverte) — jamais saisie ni fermée par un effet de bord."""
        self.assertFalse(self.grille.date_fin)

    def test_date_fin_derivee_du_debut_de_la_grille_suivante(self):
        """date_fin d'une grille = date_debut de la grille suivante du même
        régime — recalculée à la volée, jamais stockée ni fermée à la main."""
        grille_2025 = self.env['grille.prix'].create({'name': 'Grille 2025', 'date_debut': date(2025, 1, 1)})

        self.assertEqual(self.grille.date_fin, date(2025, 1, 1))
        self.assertFalse(grille_2025.date_fin, 'la plus récente reste ouverte')

    def test_date_fin_derivee_scopee_par_regime(self):
        """La dérivation ne regarde que les grilles DU MÊME RÉGIME : une
        grille Moulin n'influence jamais la date_fin dérivée d'une grille
        standard, et réciproquement (CONTEXT.md « Régime de prix »)."""
        standard_ouverte = self.env['grille.prix'].create({'name': 'Standard 2025', 'date_debut': date(2025, 1, 1)})
        moulin_1 = self.env['grille.prix'].create(
            {'name': 'Moulin 2025', 'date_debut': date(2025, 1, 1), 'regime_prix': 'moulin'}
        )
        self.assertFalse(standard_ouverte.date_fin, "la grille Moulin n'affecte pas la grille standard")

        self.env['grille.prix'].create(
            {'name': 'Moulin 2025 bis', 'date_debut': date(2025, 6, 1), 'regime_prix': 'moulin'}
        )
        self.assertEqual(moulin_1.date_fin, date(2025, 6, 1))
        self.assertFalse(standard_ouverte.date_fin)

    def test_creer_une_grille_plus_recente_ne_leve_jamais_de_chevauchement(self):
        """Sans date_fin saisi, le chevauchement est irreprésentable (#309) :
        créer une seconde grille standard ne lève plus jamais — elle prend
        simplement le relais à sa date de début (anti-chevauchement, ancien
        comportement, supprimé)."""
        grille_bis = self.env['grille.prix'].create({'name': 'Grille 2024 Bis', 'date_debut': date(2024, 6, 1)})
        self.assertEqual(self.env['grille.prix'].get_grille_active(date(2024, 3, 1)), self.grille)
        self.assertEqual(self.env['grille.prix'].get_grille_active(date(2024, 6, 1)), grille_bis)

    def test_supprimer_la_grille_la_plus_recente_ne_laisse_pas_de_trou(self):
        """Supprimer la grille la plus récente ne laisse pas de trou de
        période — la précédente redevient en vigueur (#309 : plus de
        date_fin stockée à rouvrir manuellement)."""
        grille_recente = self.env['grille.prix'].create({'name': 'Grille 2025', 'date_debut': date(2025, 1, 1)})
        self.assertEqual(self.env['grille.prix'].get_grille_active(date(2025, 3, 1)), grille_recente)

        grille_recente.unlink()

        self.assertEqual(
            self.env['grille.prix'].get_grille_active(date(2025, 3, 1)),
            self.grille,
            'la grille précédente redevient en vigueur, aucun trou de période',
        )

    # === composants() — l'unique règle d'assemblage des prix (ADR 0029) ===

    def _prix_energie(self, composants, cadran):
        return next(c['prix_kwh'] for c in composants['energies'] if c['cadran'] == cadran)

    def test_composants_prix_energie_par_cadran(self):
        """Chaque cadran facturé sort avec son produit résolu et son prix grille."""
        base = self.grille.composants('base', 6.0)
        self.assertEqual(self._prix_energie(base, 'base'), 0.2276)

        hphc = self.grille.composants('hphc', 6.0)
        self.assertEqual([c['cadran'] for c in hphc['energies']], ['hp', 'hc'])
        self.assertEqual(self._prix_energie(hphc, 'hp'), 0.2516)
        self.assertEqual(self._prix_energie(hphc, 'hc'), 0.2032)
        produit_hp = self.env.ref('souscriptions_odoo.souscriptions_product_energie_hp')
        self.assertEqual(hphc['energies'][0]['produit'], produit_hp)

    def test_abonnement_affine_a_3kva(self):
        """À 3 kVA, le tarif vaut exactement la base (terme coef nul)."""
        composants = self.grille.composants('base', 3.0)
        self.assertAlmostEqual(composants['abonnement']['prix_jour'], ABO_BASE_3KVA_STD / 365.0, places=4)

    def test_abonnement_affine_puissance_non_3kva(self):
        """Au-dessus de 3 kVA : base + coef * (P - 3), proratisé au jour."""
        composants = self.grille.composants('base', 9.0)
        attendu_annuel = ABO_BASE_3KVA_STD + ABO_COEF_KVA_STD * (9.0 - 3.0)
        self.assertAlmostEqual(composants['abonnement']['prix_jour'], attendu_annuel / 365.0, places=4)

    def test_abonnement_affine_lineaire_dans_la_puissance(self):
        """L'écart entre deux puissances vaut coef * Δkva / 365 (forme affine)."""
        prix_6 = self.grille.composants('base', 6.0)['abonnement']['prix_jour']
        prix_9 = self.grille.composants('base', 9.0)['abonnement']['prix_jour']
        self.assertAlmostEqual(prix_9 - prix_6, ABO_COEF_KVA_STD * 3.0 / 365.0, places=6)

    def test_composants_pro_majore_abonnement_et_energie(self):
        """La majoration PRO s'applique à toute la fourniture — un seul site (ADR 0029)."""
        composants = self.grille.composants('base', 9.0, coeff_pro=15.0)
        attendu_annuel = ABO_BASE_3KVA_STD + ABO_COEF_KVA_STD * (9.0 - 3.0)
        self.assertAlmostEqual(composants['abonnement']['prix_jour'], (attendu_annuel / 365.0) * 1.15, places=4)
        self.assertAlmostEqual(self._prix_energie(composants, 'base'), 0.2276 * 1.15, places=6)

    def test_abonnement_affine_solidaire(self):
        """Le solidaire lit sa propre ligne (base + coef) via le produit du catalogue."""
        composants = self.grille.composants('base', 12.0, tarif_solidaire=True)
        attendu_annuel = ABO_BASE_3KVA_SOL + ABO_COEF_KVA_SOL * (12.0 - 3.0)
        self.assertAlmostEqual(composants['abonnement']['prix_jour'], attendu_annuel / 365.0, places=4)

    def test_abonnement_sans_ligne(self):
        """Sans ligne d'abonnement pour l'univers, l'erreur est claire."""
        self.grille.ligne_ids.filtered(
            lambda l: l.type_produit == 'abonnement' and 'solidaire' not in l.product_id.name.lower()
        ).unlink()
        with self.assertRaises(UserError):
            self.grille.composants('base', 6.0)

    def test_composants_prix_energie_manquant_leve(self):
        """Grille incomplète → échec bruyant, jamais un prix nul par défaut (ADR 0029)."""
        produit_hc = self.env.ref('souscriptions_odoo.souscriptions_product_energie_hc')
        self.grille.ligne_ids.filtered(lambda l: l.product_id == produit_hc).unlink()
        with self.assertRaises(UserError):
            self.grille.composants('hphc', 6.0)

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

    # === Contrainte 1er du mois (#309) ===

    def test_date_debut_doit_etre_le_premier_du_mois(self):
        """Un changement de grille tombe toujours un 1er du mois : aucune
        Période ne l'enjambe alors jamais (CONTEXT.md « Grille de prix »)."""
        with self.assertRaises(ValidationError):
            self.env['grille.prix'].create({'name': 'Grille mi-mois', 'date_debut': date(2025, 3, 15)})

    def test_date_debut_premier_du_mois_accepte(self):
        grille = self.env['grille.prix'].create({'name': 'Grille 1er', 'date_debut': date(2025, 3, 1)})
        self.assertEqual(grille.date_debut, date(2025, 3, 1))

    # === Régime de prix (standard | Moulin) — #105 ===

    def test_regime_prix_defaut_standard(self):
        """Une grille sans régime précisé est standard par défaut."""
        self.assertEqual(self.grille.regime_prix, 'standard')

    def test_grilles_moulin_et_standard_coexistent(self):
        """Deux grilles ouvertes de régimes différents, mêmes dates, coexistent :
        chaque régime se sélectionne indépendamment (CONTEXT.md « Régime de prix »)."""
        grille_moulin = self.env['grille.prix'].create(
            {
                'name': 'Grille Moulin 2024',
                'date_debut': date(2024, 1, 1),
                'regime_prix': 'moulin',
            }
        )
        self.assertEqual(grille_moulin.regime_prix, 'moulin')
        # La grille standard n'a pas été affectée par la création de la Moulin.
        self.assertFalse(self.grille.date_fin)

    def test_get_grille_active_par_regime(self):
        """La sélection se fait par (régime, date) : standard et Moulin sont
        résolus indépendamment, même sur des dates identiques."""
        grille_moulin = self.env['grille.prix'].create(
            {
                'name': 'Grille Moulin 2024',
                'date_debut': date(2024, 1, 1),
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
                'regime_prix': 'moulin',
            }
        )
        action = grille_moulin.dupliquer_cette_grille()
        nouvelle = self.env['grille.prix'].browse(action['res_id'])
        self.assertEqual(nouvelle.regime_prix, 'moulin')

    def test_dupliquer_grille_ne_perime_pas_la_sœur(self):
        """La copie est un brouillon inactif : dupliquer une grille ouverte ne
        ferme pas la grille en cours (ancien comportement corrigé)."""
        grille_active = self.env['grille.prix'].create(
            {
                'name': 'Grille juin 2025',
                'date_debut': date(2025, 6, 1),
                'regime_prix': 'standard',
            }
        )
        action = grille_active.dupliquer_cette_grille()
        nouvelle = self.env['grille.prix'].browse(action['res_id'])

        self.assertFalse(nouvelle.active, 'La copie doit être un brouillon inactif')
        self.assertFalse(grille_active.date_fin, "La grille d'origine ne doit pas être fermée")

    def test_dupliquer_grille_propose_le_premier_du_mois_suivant(self):
        """L'action propose date_debut = 1er du mois suivant (jamais `today`,
        qui violerait la contrainte 1er-du-mois tout jour sauf le 1er, #309)."""
        action = self.grille.dupliquer_cette_grille()
        nouvelle = self.env['grille.prix'].browse(action['res_id'])
        self.assertEqual(nouvelle.date_debut.day, 1)

    def test_dupliquer_puis_activer_ne_chevauche_ni_ne_laisse_de_grille_ouverte(self):
        """Dupliquer puis activer une grille ne produit ni chevauchement ni
        grille laissée ouverte : la copie prend le relais de l'originale à
        sa date de début (#309)."""
        action = self.grille.dupliquer_cette_grille()
        copie = self.env['grille.prix'].browse(action['res_id'])

        copie.active = True  # l'utilisateur active la copie après ajustement

        self.assertEqual(self.grille.date_fin, copie.date_debut, "l'originale se termine où la copie commence")
        self.assertFalse(copie.date_fin, 'la copie, la plus récente, reste ouverte')
