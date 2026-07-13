{
    'name': 'Souscriptions Électricité',
    'version': '19.0.1.14.0',
    'depends': ['base', 'mail', 'contacts', 'account', 'base_iban', 'portal'],
    'author': 'Virgile Daugé',
    'category': 'Energy',
    'license': 'AGPL-3',
    'description': """
Gestion des souscriptions électriques

Module principal pour la gestion des contrats de fourniture d'électricité.
Remplace le module abonnement standard d'Odoo qui n'est pas adapté aux
spécificités de la fourniture d'électricité.

Fonctionnalités :

- Gestion des contrats de souscription avec cadrans énergétiques
- Périodes de facturation mensuelles avec support lissage
- Intégration avec la facturation Odoo
- Support facturation HP/HC et Base
- Régularisation des contrats lissés

Les calculs métier et l'ingestion des données Enedis (périmètre, prestations,
index, TURPE, accise) sont délégués à electricore, qui alimente les périodes
de facturation via son API.

Le pull des méta-périodes (action facturiste « Récupérer les périodes du
mois ») consomme le paquet PyPI épinglé ``electricore-client`` (voir
requirements.txt). Ce paquet n'est volontairement PAS déclaré en
``external_dependencies`` : Odoo vérifie l'importabilité de ces paquets à
l'installation et ferait échouer le module entier sur toute instance qui ne
l'a pas encore — alors que l'AC de l'issue #77 demande un module
*installable* avec un message clair si le paquet manque. La garde d'import
vit dans models/wizard/ et ne lève qu'au clic sur l'action du wizard.
""",
    'installable': True,
    'application': True,
    'auto_install': False,
    # Journal « Chèques énergie » + compte « à recevoir de l'État » (#170, ADR
    # 0026) : posés en Python (hooks.setup_cheque_energie_compta), pas en
    # data/*.xml — cf. docstring de hooks.py pour le pourquoi.
    'post_init_hook': 'setup_cheque_energie_compta',
    'data': [
        # Phase 1 - Core (toujours actif)
        'security/souscriptions_groups.xml',
        'security/ir.model.access.csv',
        'security/security_rules.xml',
        'data/souscription_sequence.xml',
        'data/produits_abonnement_simple.xml',
        'data/produits_energie.xml',
        'data/produits_prestation.xml',
        'data/raccordement_sequence.xml',
        'data/raccordement_stages.xml',
        'data/ir_cron_poll_affaires_enedis.xml',
        'data/mail_templates_raccordement.xml',
        'reports/souscription_conditions_particulieres_report.xml',
        'reports/souscription_attestation_report.xml',
        'reports/facture_energie_template.xml',
        'data/mail_templates_bienvenue.xml',
        'views/core/souscription_views.xml',
        'views/core/souscription_chronologie_views.xml',
        'views/core/res_partner_views.xml',
        'views/core/grille_prix_views.xml',
        'views/wizard/souscription_pull_meta_periodes_wizard_views.xml',
        'views/core/souscriptions_periode_views.xml',
        'views/core/souscription_refacturation_views.xml',
        'views/core/souscription_regularisation_views.xml',
        'views/wizard/souscription_pull_meta_periodes_wizard_views.xml',
        'views/core/souscription_campagne_views.xml',
        'views/core/souscription_cheque_energie_views.xml',
        'views/core/account_move_views.xml',
        'views/portal_templates.xml',
        'views/raccordement/raccordement_demande_views.xml',
        'views/raccordement/raccordement_menu.xml',
    ],
    'demo': [
        'demo/grille_prix_demo.xml',
        'demo/souscriptions_demo.xml',
        'demo/consentement_demo.xml',
        'demo/prestations_demo.xml',
        'demo/raccordement_demo.xml',
    ],
    'assets': {
        # Bundle de marque partagé par les rapports PDF (facture, conditions
        # particulières, attestation). Injecté dans le <head> du rapport.
        'web.report_assets_common': [
            'souscriptions_odoo/static/src/scss/report_brand.scss',
        ],
    },
}
