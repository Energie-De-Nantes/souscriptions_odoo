from odoo import models, fields
import pandas as pd

class MesureIndexImporter(models.TransientModel):
    _name = "metier.mesure.index.importer"
    _description = "Importateur d'index mensuels"

    fichier = fields.Binary(string="Fichier .parquet", required=True)
    filename = fields.Char(string="Nom du fichier")

    def _parse_parquet_file(self):
        import pandas as pd, base64, io
        content = base64.b64decode(self.fichier)
        buffer = io.BytesIO(content)
        return pd.read_parquet(buffer)

    def action_import(self):
        df = self._parse_parquet_file()
        df = df.where(pd.notna(df), None)
        model = self.env['metier.mesure.index']
        sous_model = self.env['souscription']
        count = 0

        for _, row in df.iterrows():
            pdl = row['pdl']
            date = row['Date_Releve']

            # Trouve une souscription active à cette date
            sous = sous_model.search([
                ('pdl', '=', pdl),
                ('date_debut', '<=', date),
                '|', ('date_fin', '>=', date), ('date_fin', '=', False)
            ], limit=1)

            if not sous:
                continue

            model.create({
                'souscription_id': sous.id,
                'date': date,
                'pdl': row.get('pdl'),
                'hph': row.get('HPH'),
                'hpb': row.get('HPB'),
                'hch': row.get('HCH'),
                'hcb': row.get('HCB'),
                'hp': row.get('HP'),
                'hc': row.get('HC'),
                'base': row.get('BASE'),
                'source': row.get('Source')
            })
            count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': "Import terminé",
                'message': f"{count} lignes importées.",
                'type': 'success',
                'sticky': False,
            }
        }