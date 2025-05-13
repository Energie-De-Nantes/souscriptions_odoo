{
    "name": "Souscriptions",
    "version": "0.1.0",
    "depends": ["base", "mail", "contacts", "account"],
    "author": "Virgile Daugé",
    "category": "Category",
    "license": "AGPL-3",
    "description": """
        Description text
    """,
    "installable": True,
    "application": True,
    "auto_install": False, 

    "data": [
        "security/ir.model.access.csv",
        "data/souscription_sequence.xml",
        
        "data/souscription_etat_data.xml",
        "data/produits_abonnement.xml",

        "views/souscription_views.xml",
        "views/souscriptions_periode_views.xml",

        'views/metier_perimetre.xml',

    ],
}
