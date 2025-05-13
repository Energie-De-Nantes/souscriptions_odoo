import pandas as pd
from odoo import models, fields, api
import base64
import io
import math
from datetime import datetime

def is_valid(value):
    if pd.isna(value):
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    return True

def sanitize_value(val):
    if isinstance(val, datetime) and val.tzinfo:
        return val.replace(tzinfo=None)
    return val

class MetierPerimetreImporter(models.TransientModel):
    _name = "metier.perimetre.importer"
    _description = "Importateur de fichier Parquet pour périmètre"

    fichier = fields.Binary(string="Fichier .parquet", required=True)
    filename = fields.Char(string="Nom du fichier")

    def _parse_parquet_file(self):
        content = base64.b64decode(self.fichier)
        buffer = io.BytesIO(content)
        return pd.read_parquet(buffer, engine='fastparquet')

    def action_import(self):
        df = self._parse_parquet_file()
        nb_total = len(df)
        nb_imported = 0
        nb_skipped = 0

        model = self.env['metier.perimetre']
        fields_dict = self.env['metier.perimetre']._fields

        for _, row in df.iterrows():
            if model.search([
                ('ref_situation_contractuelle', '=', row['Ref_Situation_Contractuelle']),
                ('date_evenement', '=', row['Date_Evenement'])
            ], limit=1):
                nb_skipped += 1
                continue

            # Convertit la Series pandas en dict Odoo compatible
            row_dict = row.to_dict()

            # Garde uniquement les champs valides du modèle
            valid_data = {
                key.lower(): sanitize_value(val) for key, val in row_dict.items()
                if key.lower() in fields_dict and is_valid(val)
            }

            model.create(valid_data)
            nb_imported += 1


        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': "Import terminé",
                'message': f"{nb_imported} lignes importées, {nb_skipped} doublons ignorés.",
                'type': 'success',
                'sticky': False,
            }
        }
