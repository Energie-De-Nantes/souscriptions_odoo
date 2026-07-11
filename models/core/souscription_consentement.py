from odoo import api, fields, models
from odoo.exceptions import UserError

# Version courante du texte de consentement affiché au·à la souscripteur·rice.
# Référencée par chaque ligne du journal pour garantir l'intégrité entre le texte
# montré et la preuve conservée (ADR 0017). À incrémenter quand le texte change.
CONSENT_TEXT_VERSION = '2026-06-v1'

# Finalités des actes d'adhésion contractuels : irrévocables (ADR 0027) — un
# « retrait » d'acceptation CGV ou de renonciation à la rétractation est
# juridiquement absurde (on ne retire pas une signature). Distinctes des
# finalités de consentement RGPD (révocables), au sein du même journal.
FINALITES_IRREVOCABLES = ('acceptation_cgv', 'renonciation_retractation')


class SouscriptionConsentement(models.Model):
    """Journal **append-only** des *Actes* du·de la *souscripteur·rice*
    (« Journal des actes », ADR 0027 ; le nom technique du modèle reste
    ``souscription.consentement``, historique).

    Deux natures d'actes, distinguées par ``finalite`` :
    - **consentement RGPD** (art. 6-1-a) — collecte chez Enedis de données
      plus fines que l'index (consommations quotidiennes, courbe de charge) :
      **révocable**, un retrait crée une ligne ;
    - **acte d'adhésion contractuel** (acceptation CGV, renonciation au délai
      de rétractation) — **irrévocable** : le retrait est refusé (voir
      ``create``).

    Possédé par la *Souscription* (ADR 0017). L'état courant d'une finalité
    est sa **dernière** ligne ; write/unlink restent interdits (append-only).
    """

    _name = 'souscription.consentement'
    _description = "Journal des actes (consentements RGPD et actes d'adhésion)"
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
            ('acceptation_cgv', 'Acceptation des CGV'),
            ('renonciation_retractation', 'Renonciation au délai de rétractation'),
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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('etat') == 'retire' and vals.get('finalite') in FINALITES_IRREVOCABLES:
                raise UserError(
                    f"« {vals['finalite']} » est un acte d'adhésion irrévocable : on ne "
                    '« retire » pas une signature (ADR 0027).'
                )
        return super().create(vals_list)

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
