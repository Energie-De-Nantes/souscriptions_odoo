"""
Helpers et mixins communs pour les tests du module souscriptions.
"""

from odoo.tests.common import TransactionCase
from datetime import date, timedelta


# Tarifs annuels d'abonnement par puissance (€/an) utilisés dans les tests.
ABO_ANNUEL_STD = {
    '3': 150.0, '6': 186.0, '9': 222.0, '12': 258.0, '15': 294.0,
    '18': 330.0, '24': 402.0, '30': 474.0, '36': 546.0,
}
ABO_ANNUEL_SOL = {
    '3': 120.0, '6': 150.0, '9': 180.0, '12': 210.0, '15': 240.0,
    '18': 270.0, '24': 330.0, '30': 390.0, '36': 450.0,
}


def build_grille_lignes(env, grille, *, prix_base, prix_hp, prix_hc,
                        abo_std=None, abo_sol=None):
    """Crée les lignes d'une grille : abonnement par puissance + énergies.

    Centralise la construction des lignes pour éviter la duplication et garder
    une source unique des tarifs attendus dans les assertions.
    """
    abo_std = ABO_ANNUEL_STD if abo_std is None else abo_std
    abo_sol = ABO_ANNUEL_SOL if abo_sol is None else abo_sol
    std = env.ref('souscriptions_odoo.souscriptions_product_abonnement_standard')
    sol = env.ref('souscriptions_odoo.souscriptions_product_abonnement_solidaire')
    base = env.ref('souscriptions_odoo.souscriptions_product_energie_base')
    hp = env.ref('souscriptions_odoo.souscriptions_product_energie_hp')
    hc = env.ref('souscriptions_odoo.souscriptions_product_energie_hc')

    vals = []
    for puissance, prix in abo_std.items():
        vals.append({
            'grille_id': grille.id, 'product_id': std.id,
            'type_produit': 'abonnement', 'puissance': puissance,
            'prix_abonnement_annuel': prix,
        })
    for puissance, prix in abo_sol.items():
        vals.append({
            'grille_id': grille.id, 'product_id': sol.id,
            'type_produit': 'abonnement', 'puissance': puissance,
            'prix_abonnement_annuel': prix,
        })
    vals += [
        {'grille_id': grille.id, 'product_id': base.id,
         'type_produit': 'energie', 'prix_unitaire': prix_base},
        {'grille_id': grille.id, 'product_id': hp.id,
         'type_produit': 'energie', 'prix_unitaire': prix_hp},
        {'grille_id': grille.id, 'product_id': hc.id,
         'type_produit': 'energie', 'prix_unitaire': prix_hc},
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
        cls.partner_test = cls.env['res.partner'].create({
            'name': 'Client Test Standard',
            'is_company': False,
            'street': '123 rue de Test',
            'city': 'TestVille', 
            'zip': '12345',
            'country_id': cls.env.ref('base.fr').id,
            'email': 'test@example.com',
        })
        
        # Client entreprise
        cls.partner_company = cls.env['res.partner'].create({
            'name': 'Entreprise Test SARL',
            'is_company': True,
            'street': '456 avenue du Test',
            'city': 'TestVille Pro',
            'zip': '67890',
            'country_id': cls.env.ref('base.fr').id,
        })
        
        # État de facturation
        cls.etat_facturation = cls.env['souscription.etat'].create({
            'name': 'Test État',
            'sequence': 10,
        })
        
        # Grille de prix active avec lignes, pour que la facturation
        # fonctionne sans dépendre des données de démo
        cls.env['grille.prix'].search([('is_current', '=', True)]).write({'is_current': False})
        cls.grille_prix = cls.env['grille.prix'].create({
            'name': 'Grille Test',
            'date_debut': date(2024, 1, 1),
            'date_fin': date(2024, 12, 31),
            'active': True,
            'is_current': True,
        })
        build_grille_lignes(
            cls.env, cls.grille_prix,
            prix_base=0.15, prix_hp=0.18, prix_hc=0.12,
        )
        
        # Souscription Base standard
        cls.souscription_base = cls.env['souscription.souscription'].create({
            'partner_id': cls.partner_test.id,
            'pdl': 'PDL_TEST_STANDARD',
            'puissance_souscrite': '6',
            'type_tarif': 'base',
            'etat_facturation_id': cls.etat_facturation.id,
            'date_debut': date(2024, 1, 1),
            'provision_mensuelle_kwh': 300.0,
            'ref_compteur': 'COMP_TEST_001',
        })
        
        # Souscription HP/HC
        cls.souscription_hphc = cls.env['souscription.souscription'].create({
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
        })
    
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
            **kwargs  # Les kwargs écrasent les defaults
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
        
        facture = souscription._creer_facture_periode(periode)
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
            self.assertIn(expected_section, section_names, 
                         f"Section '{expected_section}' manquante")
        
        # Vérifier les notes TURPE
        notes = lines.filtered(lambda l: l.display_type == 'line_note')
        turpe_notes = [n for n in notes if 'turpe' in n.name.lower()]
        
        self.assertGreaterEqual(len(turpe_notes), expected_notes,
                               f"Au moins {expected_notes} notes TURPE attendues")
        
        # Vérifier les lignes produit
        product_lines = lines.filtered(lambda l: l.display_type == 'product')
        self.assertGreater(len(product_lines), 0, "Au moins une ligne produit attendue")


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