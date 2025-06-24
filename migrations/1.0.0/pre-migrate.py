# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    """
    Migration du modèle 'souscription' vers 'souscription.souscription'
    """
    # Vérifier si l'ancienne table existe
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'souscription'
        );
    """)
    if cr.fetchone()[0]:
        # Renommer la table
        cr.execute("ALTER TABLE souscription RENAME TO souscription_souscription;")
        
        # Mettre à jour les références dans ir_model
        cr.execute("""
            UPDATE ir_model 
            SET model = 'souscription.souscription' 
            WHERE model = 'souscription';
        """)
        
        # Mettre à jour les références dans ir_model_fields
        cr.execute("""
            UPDATE ir_model_fields 
            SET model = 'souscription.souscription' 
            WHERE model = 'souscription';
        """)
        
        # Mettre à jour les références dans ir_model_fields pour les relations
        cr.execute("""
            UPDATE ir_model_fields 
            SET relation = 'souscription.souscription' 
            WHERE relation = 'souscription';
        """)
        
        # Mettre à jour les ACL
        cr.execute("""
            UPDATE ir_model_access 
            SET model_id = (SELECT id FROM ir_model WHERE model = 'souscription.souscription' LIMIT 1)
            WHERE model_id = (SELECT id FROM ir_model WHERE model = 'souscription' LIMIT 1);
        """)