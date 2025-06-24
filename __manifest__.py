{
    "name": "Souscriptions",
    "version": "1.0.0",
    "depends": ["base", "mail", "contacts", "account"],
    "author": "Virgile Daugé",
    "category": "Energy",
    "license": "AGPL-3",
    "description": """
        Gestion des souscriptions électriques
        
        Module principal pour la gestion des contrats de fourniture d'électricité.
        Remplace le module abonnement standard d'Odoo qui n'est pas adapté 
        aux spécificités de la fourniture d'électricité.
        
        Fonctionnalités Core :
        - Gestion des contrats de souscription avec cadrans énergétiques
        - Périodes de facturation mensuelles avec support lissage
        - Intégration avec la facturation Odoo
        - Support facturation HP/HC et Base
        - Régularisation des contrats lissés
        
        Fonctionnalités Métier (Phase 2) :
        - Import de données Enedis (périmètre, prestations, index)
        - Intégration avec données métier externes
        - Rapports étendus avec historique complet
    """,
    "installable": True,
    "application": True,
    "auto_install": False, 

    "data": [
        # Phase 1 - Core (toujours actif)
        "security/ir.model.access.csv",
        "data/souscription_sequence.xml",
        "data/souscription_etat_data.xml",
        "data/produits_abonnement_simple.xml",
        "data/produits_energie.xml",
        "data/grille_prix_demo.xml",
        "report/souscription_contrat_report.xml",
        # "reports/facture_energie_template.xml",  # Temporairement désactivé
        "views/core/souscription_views.xml",
        "views/core/grille_prix_views.xml",
        "views/core/souscriptions_periode_views.xml",
        
        # Phase 2 - Métier (à décommenter lors de l'activation)
        # "security/ir.model.access.metier.csv",
        # "views/metier/metier_perimetre.xml",
        # "views/metier/metier_prestation.xml",
        # "views/metier/metier_mesure_index.xml",
    ],
    
    "demo": [
        "demo/souscriptions_demo.xml",
    ],
}
