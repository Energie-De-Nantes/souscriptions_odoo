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
    # Integer (#132) : le contrat electricore (index_*_kwh) normalise l'index en
    # kWh entier par floor au boundary d'ingestion (ADR-0034 côté electricore) ;
    # contrairement aux énergies (`energie_*_kwh`) et montants (`*_eur`), qui
    # restent Float, la résolution sub-kWh n'existe plus pour un index.
    index_hph = fields.Integer(string='Index HPH', help='Heures Pleines saison Haute')
    index_hpb = fields.Integer(string='Index HPB', help='Heures Pleines saison Basse')
    index_hch = fields.Integer(string='Index HCH', help='Heures Creuses saison Haute')
    index_hcb = fields.Integer(string='Index HCB', help='Heures Creuses saison Basse')
    index_hp = fields.Integer(string='Index HP')
    index_hc = fields.Integer(string='Index HC')
    index_base = fields.Integer(string='Index Base')

    # Provenance du justificatif côté electricore (#76, ADR 0020 §6) :
    # `releve_externe_id` (← `releve_id` du contrat v3) identifie le relevé
    # source, support de la **dédup au re-pull** ; `origine` (← `origine_releve`,
    # précisé par `evenement` pour les relevés d'événement C15) documente sa
    # nature (flux, événement…).
    releve_externe_id = fields.Char(
        string='ID relevé externe',
        help='Identifiant du relevé côté electricore (releve_id du contrat), support de la dédup au re-pull.',
    )
    origine = fields.Char(
        string='Origine',
        help='Provenance du relevé côté electricore (origine_releve, précisée par evenement '
        "pour les relevés d'événement C15).",
    )

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
