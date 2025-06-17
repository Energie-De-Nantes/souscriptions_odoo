import pandas as pd
import base64
import io
from datetime import datetime
from odoo import models, fields, api
import math

# from electricore.core.périmètre.fonctions import extraire_modifications_impactantes

def is_valid(value):
    return not pd.isna(value) and not (isinstance(value, float) and math.isnan(value))

def sanitize_value(val):
    if isinstance(val, datetime) and val.tzinfo:
        return val.date()
    return val

class MetierPrestationImporter(models.TransientModel):
    _name = "metier.prestation.importer"
    _description = "Importateur de fichier Parquet pour prestations"

    fichier = fields.Binary(string="Fichier .parquet", required=True)
    filename = fields.Char(string="Nom du fichier")

    def _parse_parquet_file(self):
        content = base64.b64decode(self.fichier)
        buffer = io.BytesIO(content)
        return pd.read_parquet(buffer, engine='fastparquet')

    def action_import(self):
        df = self._parse_parquet_file()

        df.columns = [col.lower().replace("é", "e").replace("è", "e").replace("ê", "e")
                      .replace("à", "a").replace("ç", "c") for col in df.columns]

        # mi = extraire_modifications_impactantes(df)
        model = self.env['metier.prestation']
        fields_dict = model._fields

        nb_total = len(df)
        nb_imported = 0
        nb_skipped = 0

        for _, row in df.iterrows():
            row_dict = row.to_dict()
            if model.search([
                ('id_ev', '=', row_dict.get('id_ev')),
                ('pdl', '=', row_dict.get('pdl')),
                ('date_facture', '=', row_dict.get('Date_Facture'))
            ], limit=1):
                nb_skipped += 1
                continue

            valid_data = {
                key: sanitize_value(val)
                for key, val in row_dict.items()
                if key in fields_dict and is_valid(val)
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
