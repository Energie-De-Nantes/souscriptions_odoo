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

        RENAME_COLUMNS = {
            col: col.lower().replace("à", "a").replace("è", "e").replace("é", "e").replace("ê", "e").replace("ç", "c")
            for col in df.columns
        }
        df.rename(columns=RENAME_COLUMNS, inplace=True)
        nb_total = len(df)
        nb_imported = 0
        nb_skipped = 0

        model = self.env['metier.perimetre']
        fields_dict = self.env['metier.perimetre']._fields

        index_model = self.env['metier.mesure.index']
        sous_model = self.env['souscription']

        for _, row in df.iterrows():
            if model.search([
                ('ref_situation_contractuelle', '=', row['ref_situation_contractuelle']),
                ('date_evenement', '=', row['date_evenement'])
            ], limit=1):
                nb_skipped += 1
                continue
            index_avant = None
            
            # Création index AVANT
            if is_valid(row.get('avant_date_releve')):
                date = row['avant_date_releve']
                index_avant = index_model.create({
                    'date': date,
                    'pdl': row['pdl'],
                    'hph': row.get('avant_hph'),
                    'hpb': row.get('avant_hpb'),
                    'hch': row.get('avant_hch'),
                    'hcb': row.get('avant_hcb'),
                    'source': 'périmètre',
                    'souscription_id': (
                        sous_model.search([
                            ("pdl", "=", row.get("pdl")),
                            ("date_debut", "<=", date),
                            ("date_fin", ">", date),
                        ], limit=1).id or None
                    ),
                })
            index_apres = None
            # Création index APRES
            if is_valid(row.get('apres_date_releve')):
                date = row['apres_date_releve']
                index_apres = index_model.create({
                    'date': date,
                    'pdl': row['pdl'],
                    'hph': row.get('apres_hph'),
                    'hpb': row.get('apres_hpb'),
                    'hch': row.get('apres_hch'),
                    'hcb': row.get('apres_hcb'),
                    'source': 'périmètre',
                    'souscription_id': (
                        sous_model.search([
                            ("pdl", "=", row.get("pdl")),
                            ("date_debut", "<=", date),
                            ("date_fin", ">", date),
                        ], limit=1).id or None
                    ),
                })

            # Construction du dictionnaire des données valides pour le périmètre
            valid_data = {
                key.lower(): sanitize_value(val)
                for key, val in row.to_dict().items()
                if key.lower() in fields_dict and is_valid(val)
            }

            # Liaison des index au périmètre
            valid_data["index_avant_id"] = index_avant.id if index_avant else None
            valid_data["index_apres_id"] = index_apres.id if index_apres else None

            # Création du périmètre
            model.create(valid_data)
            nb_imported += 1
