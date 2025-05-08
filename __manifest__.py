{
    "name": "Souscriptions",
    "version": "0.1.0",
    "depends": ["base", "contacts"],
    "author": "Virgile Daugé",
    "category": "Category",
    "license": "AGPL-3",
    "description": """
        Description text
    """,
    "installable": True,
    "application": True,
    "auto_install": False, 

    'data': [
        'security/ir.model.access.csv',
        'views/souscription_views.xml',
        'data/souscription_etat_data.xml',
    ],
}
