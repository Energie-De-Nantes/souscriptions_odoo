from odoo import api, fields, models
from odoo.exceptions import UserError


class SouscriptionReleve(models.Model):
    """Relevé d'index : événement de lecture daté du compteur, enfant d'une
    *Période* (ADR 0015). Forme **large, par cadran réseau** — un record porte un
    index par registre physique du compteur (HPH/HPB/HCH/HCB, ou HP/HC, ou Base),
    jamais par cadran *facturé*. Cardinalité variable (≈2 en régime normal, 3–4
    lors d'un changement de compteur), représentée fidèlement sans branche
    spéciale. Justificatif légal du calcul d'énergie, support de vérification par
    le·la souscripteur·rice ; jamais matérialisé en account.move.line.
    """

    _name = 'souscription.releve'
    _description = "Relevé d'index"
    _order = 'date, id'

    periode_id = fields.Many2one(
        'souscription.periode',
        string='Période',
        required=True,
        ondelete='cascade',
        index=True,
    )

    # Calendrier de comptage de la Période (ADR 0005) : pilote les colonnes
    # d'index pertinentes à la saisie / à l'affichage.
    config_cadrans = fields.Selection(related='periode_id.config_cadrans', readonly=True)

    date = fields.Date(required=True)

    # Mesure Enedis (reel) vs estimation electricore/facturiste (estime) :
    # étiquetée sur la facture (obligation légale d'affichage de l'index estimé).
    nature = fields.Selection(
        [('reel', 'Réel'), ('estime', 'Estimé')],
        string='Nature',
        required=True,
        default='reel',
    )

    # Index par cadran réseau (même axe mesuré que energie_*) — colonnes
    # pertinentes selon config_cadrans : 4_cadrans → HPH/HPB/HCH/HCB ;
    # hp_hc → HP/HC ; base → Base.
    index_hph = fields.Float(string='Index HPH', help='Heures Pleines saison Haute')
    index_hpb = fields.Float(string='Index HPB', help='Heures Pleines saison Basse')
    index_hch = fields.Float(string='Index HCH', help='Heures Creuses saison Haute')
    index_hcb = fields.Float(string='Index HCB', help='Heures Creuses saison Basse')
    index_hp = fields.Float(string='Index HP')
    index_hc = fields.Float(string='Index HC')
    index_base = fields.Float(string='Index Base')

    # Verrou de facturation étendu à l'enfant (#56 / ADR 0014-0015). Symétrique du
    # verrou _LOCKED_FIELDS de la Période : dès qu'une Période est facturée
    # (facture_id existe, brouillon de facture compris), ses relevés sont figés —
    # sinon le justificatif d'index pourrait diverger silencieusement de la facture
    # émise. Pour corriger : supprimer la facture (défige) ou émettre une
    # régularisation.
    def _check_periode_non_facturee(self, periodes):
        for periode in periodes:
            if periode.facture_id:
                raise UserError(
                    f'Période {periode.mois_annee} : déjà facturée, modification des relevés '
                    'interdite. Supprimez la facture pour corriger, ou créez une régularisation.'
                )

    @api.model_create_multi
    def create(self, vals_list):
        periodes = self.env['souscription.periode'].browse(
            [vals['periode_id'] for vals in vals_list if vals.get('periode_id')]
        )
        self._check_periode_non_facturee(periodes)
        return super().create(vals_list)

    def write(self, vals):
        self._check_periode_non_facturee(self.periode_id)
        # Un déplacement vers une autre Période facturée est aussi interdit.
        if vals.get('periode_id'):
            self._check_periode_non_facturee(self.env['souscription.periode'].browse(vals['periode_id']))
        return super().write(vals)

    def unlink(self):
        self._check_periode_non_facturee(self.periode_id)
        return super().unlink()
