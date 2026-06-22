"""
Helpers et mixins communs pour les tests du module souscriptions.
"""

from datetime import date

from odoo.tests.common import TransactionCase

# Tarif d'abonnement affine (ADR 0018) : base 3 kVA + coefficient par kVA.
# prix_an(P) = base + coef * (P - 3)
ABO_BASE_3KVA_STD = 150.0
ABO_COEF_KVA_STD = 12.0
ABO_BASE_3KVA_SOL = 120.0
ABO_COEF_KVA_SOL = 10.0


def abo_annuel_std(puissance_kva):
    """Tarif annuel standard attendu (€/an) pour une puissance, selon l'affine."""
    return ABO_BASE_3KVA_STD + ABO_COEF_KVA_STD * (float(puissance_kva) - 3.0)


def abo_annuel_sol(puissance_kva):
    """Tarif annuel solidaire attendu (€/an) pour une puissance, selon l'affine."""
    return ABO_BASE_3KVA_SOL + ABO_COEF_KVA_SOL * (float(puissance_kva) - 3.0)


# Tarifs annuels par puissance dérivés de l'affine, pour les assertions des tests
# qui raisonnent encore en €/an par palier (le tarif est désormais calculé, pas
# énuméré dans la grille).
_PUISSANCES = ('3', '6', '9', '12', '15', '18', '24', '30', '36')
ABO_ANNUEL_STD = {p: abo_annuel_std(p) for p in _PUISSANCES}
ABO_ANNUEL_SOL = {p: abo_annuel_sol(p) for p in _PUISSANCES}


def build_grille_lignes(
    env,
    grille,
    *,
    prix_base,
    prix_hp,
    prix_hc,
    base_std=ABO_BASE_3KVA_STD,
    coef_std=ABO_COEF_KVA_STD,
    base_sol=ABO_BASE_3KVA_SOL,
    coef_sol=ABO_COEF_KVA_SOL,
):
    """Crée les 8 lignes d'une grille : 2 abonnement (affine) + 6 énergie.

    L'abonnement est une ligne par univers (ADR 0018) portant le tarif affine
    base 3 kVA + coefficient par kVA ; l'univers est porté par le produit du
    catalogue (ADR 0013), jamais ré-encodé ici. Énergies inchangées.
    """
    std = env.ref('souscriptions_odoo.souscriptions_product_abonnement_standard')
    sol = env.ref('souscriptions_odoo.souscriptions_product_abonnement_solidaire')
    base = env.ref('souscriptions_odoo.souscriptions_product_energie_base')
    hp = env.ref('souscriptions_odoo.souscriptions_product_energie_hp')
    hc = env.ref('souscriptions_odoo.souscriptions_product_energie_hc')
    base_sol_prod = env.ref('souscriptions_odoo.souscriptions_product_energie_base_solidaire')
    hp_sol = env.ref('souscriptions_odoo.souscriptions_product_energie_hp_solidaire')
    hc_sol = env.ref('souscriptions_odoo.souscriptions_product_energie_hc_solidaire')

    vals = [
        {
            'grille_id': grille.id,
            'product_id': std.id,
            'type_produit': 'abonnement',
            'prix_base_3kva': base_std,
            'coef_kva': coef_std,
        },
        {
            'grille_id': grille.id,
            'product_id': sol.id,
            'type_produit': 'abonnement',
            'prix_base_3kva': base_sol,
            'coef_kva': coef_sol,
        },
    ]
    vals += [
        {'grille_id': grille.id, 'product_id': base.id, 'type_produit': 'energie', 'prix_unitaire': prix_base},
        {'grille_id': grille.id, 'product_id': hp.id, 'type_produit': 'energie', 'prix_unitaire': prix_hp},
        {'grille_id': grille.id, 'product_id': hc.id, 'type_produit': 'energie', 'prix_unitaire': prix_hc},
        # Jumeaux solidaires (ADR 0013) : mêmes prix énergie, produits isolés.
        {'grille_id': grille.id, 'product_id': base_sol_prod.id, 'type_produit': 'energie', 'prix_unitaire': prix_base},
        {'grille_id': grille.id, 'product_id': hp_sol.id, 'type_produit': 'energie', 'prix_unitaire': prix_hp},
        {'grille_id': grille.id, 'product_id': hc_sol.id, 'type_produit': 'energie', 'prix_unitaire': prix_hc},
    ]
    return env['grille.prix.ligne'].create(vals)


class SouscriptionsTestMixin:
    """Mixin commun pour les tests de souscriptions avec données partagées."""

    @classmethod
    def setUpSouscriptionsData(cls):
        """
        Setup des données communes de test pour souscriptions.
        À appeler dans setUpClass ou setUp des tests qui en ont besoin.
        """
        # Client de test standard
        cls.partner_test = cls.env['res.partner'].create(
            {
                'name': 'Client Test Standard',
                'is_company': False,
                'street': '123 rue de Test',
                'city': 'TestVille',
                'zip': '12345',
                'country_id': cls.env.ref('base.fr').id,
                'email': 'test@example.com',
            }
        )

        # Client entreprise
        cls.partner_company = cls.env['res.partner'].create(
            {
                'name': 'Entreprise Test SARL',
                'is_company': True,
                'street': '456 avenue du Test',
                'city': 'TestVille Pro',
                'zip': '67890',
                'country_id': cls.env.ref('base.fr').id,
            }
        )

        # État de facturation
        cls.etat_facturation = cls.env['souscription.etat'].create(
            {
                'name': 'Test État',
                'sequence': 10,
            }
        )

        # Grille de prix active avec lignes, pour que la facturation
        # fonctionne sans dépendre des données de démo. La grille est résolue
        # par date (get_grille_active), jamais par un drapeau (ADR 0018).
        cls.grille_prix = cls.env['grille.prix'].create(
            {
                'name': 'Grille Test',
                'date_debut': date(2024, 1, 1),
                'date_fin': date(2024, 12, 31),
                'active': True,
            }
        )
        build_grille_lignes(
            cls.env,
            cls.grille_prix,
            prix_base=0.15,
            prix_hp=0.18,
            prix_hc=0.12,
        )

        # Souscription Base standard
        cls.souscription_base = cls.env['souscription.souscription'].create(
            {
                'partner_id': cls.partner_test.id,
                'pdl': 'PDL_TEST_STANDARD',
                'puissance_souscrite': '6',
                'type_tarif': 'base',
                'etat_facturation_id': cls.etat_facturation.id,
                'date_debut': date(2024, 1, 1),
                'provision_mensuelle_kwh': 300.0,
                'ref_compteur': 'COMP_TEST_001',
            }
        )

        # Souscription HP/HC
        cls.souscription_hphc = cls.env['souscription.souscription'].create(
            {
                'partner_id': cls.partner_test.id,
                'pdl': 'PDL_TEST_HPHC',
                'puissance_souscrite': '9',
                'type_tarif': 'hphc',
                'etat_facturation_id': cls.etat_facturation.id,
                'date_debut': date(2024, 1, 1),
                'provision_hp_kwh': 200.0,  # Provision HP mensuelle
                'provision_hc_kwh': 120.0,  # Provision HC mensuelle
                'lisse': True,
                'ref_compteur': 'COMP_TEST_002',
            }
        )

    def create_test_periode(self, souscription, date_debut=None, date_fin=None, **kwargs):
        """
        Helper pour créer une période de test avec des données réalistes.

        Args:
            souscription: Instance de souscription
            date_debut: Date de début (défaut: 1er du mois courant)
            date_fin: Date de fin (défaut: fin du mois)
            **kwargs: Autres champs à surcharger

        Returns:
            Instance de souscription.periode
        """
        if not date_debut:
            date_debut = date(2024, 1, 1)
        if not date_fin:
            date_fin = date(2024, 1, 31)

        jours = (date_fin - date_debut).days + 1

        # Données par défaut selon le type de tarif
        if souscription.type_tarif == 'base':
            base_kwh = kwargs.pop('base_kwh', 280.0)
            defaults = {
                'energie_hph_kwh': base_kwh * 0.5,
                'energie_hpb_kwh': base_kwh * 0.2,
                'energie_hch_kwh': base_kwh * 0.2,
                'energie_hcb_kwh': base_kwh * 0.1,
                'provision_base_kwh': base_kwh if souscription.lisse else 0,
                'turpe_fixe': 8.5,
                'turpe_variable': base_kwh * 0.015,
            }
        else:  # HP/HC
            hp_kwh = kwargs.pop('hp_kwh', 200.0)
            hc_kwh = kwargs.pop('hc_kwh', 120.0)
            defaults = {
                'energie_hph_kwh': hp_kwh * 0.6,
                'energie_hpb_kwh': hp_kwh * 0.4,
                'energie_hch_kwh': hc_kwh * 0.6,
                'energie_hcb_kwh': hc_kwh * 0.4,
                'provision_hp_kwh': hp_kwh if souscription.lisse else 0,
                'provision_hc_kwh': hc_kwh if souscription.lisse else 0,
                'turpe_fixe': 12.8,
                'turpe_variable': (hp_kwh + hc_kwh) * 0.018,
            }

        # Merger avec les kwargs fournis
        data = {
            'souscription_id': souscription.id,
            'date_debut': date_debut,
            'date_fin': date_fin,
            'type_periode': 'mensuelle',
            'jours': jours,
            **defaults,
            **kwargs,  # Les kwargs écrasent les defaults
        }

        return self.env['souscription.periode'].create(data)

    def create_test_invoice(self, souscription, periode=None, **periode_kwargs):
        """
        Helper pour créer une facture de test complète.

        Args:
            souscription: Instance de souscription
            periode: Période existante ou None pour en créer une
            **periode_kwargs: Arguments pour create_test_periode si période=None

        Returns:
            Tuple (periode, facture)
        """
        if periode is None:
            periode = self.create_test_periode(souscription, **periode_kwargs)

        facture = periode._creer_facture()
        return periode, facture

    def assert_invoice_structure(self, facture, expected_sections=None, expected_notes=None):
        """
        Helper pour vérifier la structure d'une facture d'énergie.

        Args:
            facture: Instance de account.move
            expected_sections: Liste des noms de sections attendues
            expected_notes: Nombre minimum de notes TURPE attendues
        """
        if expected_sections is None:
            expected_sections = ['Abonnement', 'Énergie']
        if expected_notes is None:
            expected_notes = 2

        lines = facture.invoice_line_ids

        # Vérifier que c'est une facture d'énergie
        self.assertTrue(facture.is_facture_energie, "Devrait être une facture d'énergie")

        # Vérifier les sections
        sections = lines.filtered(lambda l: l.display_type == 'line_section')
        section_names = [s.name for s in sections]

        for expected_section in expected_sections:
            self.assertIn(expected_section, section_names, f"Section '{expected_section}' manquante")

        # Vérifier les notes TURPE
        notes = lines.filtered(lambda l: l.display_type == 'line_note')
        turpe_notes = [n for n in notes if 'turpe' in n.name.lower()]

        self.assertGreaterEqual(len(turpe_notes), expected_notes, f'Au moins {expected_notes} notes TURPE attendues')

        # Vérifier les lignes produit
        product_lines = lines.filtered(lambda l: l.display_type == 'product')
        self.assertGreater(len(product_lines), 0, 'Au moins une ligne produit attendue')


class SouscriptionsTestCase(SouscriptionsTestMixin, TransactionCase):
    """
    Classe de base pour les tests de souscriptions.
    Combine TransactionCase avec le mixin de données communes.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()


class SouscriptionsFormTestCase(SouscriptionsTestMixin, TransactionCase):
    """
    Classe de base pour les tests de formulaires et vues.
    Peut être étendue pour ajouter des helpers spécifiques aux formulaires.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.setUpSouscriptionsData()

    def create_form_view(self, model, view_type='form', res_id=None):
        """Helper pour créer une vue formulaire en mode test."""
        Model = self.env[model]
        if res_id:
            return Model.browse(res_id)
        else:
            return Model.new()

    def assert_field_visible(self, form, field_name):
        """Vérifier qu'un champ est visible dans le formulaire."""
        # TODO: Implémenter selon les besoins
        pass

    def assert_field_readonly(self, form, field_name):
        """Vérifier qu'un champ est en lecture seule."""
        # TODO: Implémenter selon les besoins
        pass
