from . import souscription_metier_mixin

# Application automatique du mixin si le modèle souscription existe
def apply_metier_mixin():
    from odoo import api, SUPERUSER_ID
    from odoo.modules.registry import Registry
    
    try:
        # Cette fonction sera appelée lors du chargement du module
        # pour injecter le mixin dans le modèle souscription
        from odoo import models
        
        class SouscriptionWithMetier(models.Model):
            _inherit = ['souscription.souscription', 'souscription.metier.mixin']
            _name = 'souscription.souscription'
        
    except Exception:
        # Si le modèle n'existe pas encore, on ignore
        pass