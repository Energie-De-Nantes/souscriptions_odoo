from odoo import fields, models
from odoo.exceptions import UserError

# Version courante du texte de consentement affiché au·à la souscripteur·rice.
# Référencée par chaque ligne du journal pour garantir l'intégrité entre le texte
# montré et la preuve conservée (ADR 0017). À incrémenter quand le texte change.
CONSENT_TEXT_VERSION = '2026-06-v1'


class SouscriptionConsentement(models.Model):
    """Journal **append-only** du *Consentement (données de consommation)*.

    Trace l'autorisation RGPD (art. 6-1-a) donnée à EDN de faire collecter chez
    Enedis des données plus fines que l'index (consommations quotidiennes, courbe
    de charge). Possédé par la *Souscription* (ADR 0017). L'état courant d'une
    finalité est sa **dernière** ligne ; un retrait **crée** une ligne, n'écrase
    rien — d'où le verrou append-only ci-dessous (write/unlink interdits).
    """

    _name = 'souscription.consentement'
    _description = 'Journal de consentement (données de consommation)'
    _order = 'date_consentement desc, id desc'

    souscription_id = fields.Many2one(
        'souscription.souscription',
        string='Souscription',
        required=True,
        ondelete='cascade',
        index=True,
    )
    # Finalités granulaires : pas de consentement groupé (spécificité, art. 4-11).
    finalite = fields.Selection(
        [
            ('conso_quotidienne', 'Consommations quotidiennes'),
            ('courbe_charge', 'Courbe de charge'),
        ],
        string='Finalité',
        required=True,
    )
    etat = fields.Selection(
        [('donne', 'Donné'), ('retire', 'Retiré')],
        string='État',
        required=True,
        default='donne',
    )
    date_consentement = fields.Datetime(string='Horodatage', required=True, default=fields.Datetime.now)
    version_texte = fields.Char(
        string='Version du texte',
        required=True,
        default=lambda self: CONSENT_TEXT_VERSION,
        help='Version du texte de consentement affiché lors de cet acte.',
    )
    source = fields.Char(
        string='Source / canal',
        help="Origine de l'acte (formulaire public + IP, saisie back-office, retrait au portail…).",
    )
    date_retrait = fields.Date(string='Date de retrait')

    def write(self, vals):
        raise UserError(
            'Le journal de consentement est append-only : une ligne existante ne '
            'peut être modifiée. Enregistrez un nouvel acte (donné ou retiré).'
        )

    def unlink(self):
        raise UserError(
            'Le journal de consentement est append-only : une ligne ne peut être '
            'supprimée (preuve opposable, RGPD art. 7-1).'
        )
