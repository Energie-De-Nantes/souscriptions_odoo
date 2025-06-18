{
    "name": "Souscriptions Core",
    "version": "0.2.0",
    "depends": ["base", "mail", "contacts", "account"],
    "author": "Virgile Daugé",
    "category": "Energy",
    "license": "AGPL-3",
    "description": """
        Gestion des souscriptions électriques - Version minimale
        
        Module principal pour la gestion des contrats de fourniture d'électricité.
        Remplace le module abonnement standard d'Odoo qui n'est pas adapté 
        aux spécificités de la fourniture d'électricité.
        
        Fonctionnalités :
        - Gestion des contrats de souscription avec cadrans énergétiques
        - Périodes de facturation mensuelles avec support lissage
        - Intégration avec la facturation Odoo
        - API pour intégration de données externes
        - Support facturation HP/HC et Base
        - Régularisation des contrats lissés
    """,
    "installable": True,
    "application": True,
    "auto_install": False, 

    "data": [
        "security/ir.model.access.csv",
        "data/souscription_sequence.xml",
        "data/souscription_etat_data.xml",
        "data/produits_abonnement_simple.xml",
        "data/produits_energie.xml",
        "data/grille_prix_demo.xml",
        "report/souscription_contrat_report.xml",
        "views/souscription_views.xml",
        "views/grille_prix_views.xml",
        "views/souscriptions_periode_views.xml",
        
        # Données métier (à déplacer vers souscriptions_metier plus tard)
        'views/metier_perimetre.xml',
        'views/metier_prestation.xml',
        'views/metier_mesure_index.xml',
    ],
    
    "demo": [
        "demo/souscriptions_demo.xml",
    ],
}
