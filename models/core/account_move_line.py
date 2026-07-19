from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # Provenance (#266, tranche 2 du PRD #264 ; ADR 0014 amendé) : posée par
    # LA composition des lignes de facture — `souscription.periode._composer_lignes`
    # (sections, abonnement, énergie, notes TURPE), `souscription.refacturation._composer_ligne`
    # (Refacturations rassemblées) et `souscription.regularisation._composer_lignes`
    # (grille × cadran + notes par mois) — jamais par une ligne ajoutée à la
    # main par le·la facturiste, ni par un autre module (arrondi, escompte).
    # Enforcement DOUX (décision du PRD, jamais dévié) : readonly dans la vue
    # formulaire + garde `ondelete` ci-dessous — JAMAIS de surcharge de
    # `write()` (la voie script/RPC reste ouverte, assumée : la re-génération
    # à l'émission garantit la conformité du document final).
    # `copy=False` : un avoir ou une duplication (Odoo passe par `copy_data`)
    # ne porte jamais le flag — il ne doit jamais re-composer/se faire
    # regénérer un document qui n'est plus la source vivante.
    souscription_ligne_generee = fields.Boolean(
        string='Ligne générée (souscription)',
        copy=False,
        default=False,
        help='Posée par la composition des lignes de facture (Période, Régularisation, '
        'Refacturations rassemblées). Lecture seule en vue et suppression directe '
        'refusée (#266) ; jamais de garde sur write() — la re-génération à '
        "l'émission garantit la conformité.",
    )

    @api.ondelete(at_uninstall=False)
    def _empecher_suppression_directe_ligne_generee(self):
        """Garde étroite (#266) : refuse la suppression DIRECTE d'une ligne
        **générée** d'une facture d'**énergie** encore en **brouillon** — la
        correction passe par la source (Période/Régularisation) ou par une
        ligne manuelle dédiée, jamais par l'effacement silencieux d'une ligne
        du miroir.

        Deux échappatoires, toutes deux par contexte (jamais une surcharge de
        `write()`, décision explicite du PRD) :
        - `souscription_move_unlink` : posé par `account.move.unlink()` —
          supprimer la facture ENTIÈRE (cascade ORM sur `move_id`,
          `ondelete='cascade'`) reste le geste de correction documenté (#14) ;
        - `souscription_regenere_lignes` : posé par
          `account.move._recomposer_lignes_generees()` — la ré-génération
          elle-même doit pouvoir supprimer les lignes flaguées qu'elle
          remplace.

        Une facture déjà **postée** n'a pas besoin de cette garde :
        l'immutabilité comptable (Odoo core) bloque déjà toute suppression de
        ligne.

        Consommateur des deux clés de contexte ci-dessus : carte complète
        (« Régénération au fil de l'eau ») dans `account_move.py`."""
        if self.env.context.get('souscription_move_unlink') or self.env.context.get('souscription_regenere_lignes'):
            return
        for ligne in self:
            if ligne.souscription_ligne_generee and ligne.move_id.state == 'draft':
                raise UserError(
                    'Ligne générée automatiquement (Période ou Régularisation) : suppression '
                    "directe interdite. Elle sera recomposée depuis sa source à l'émission ; "
                    'pour une correction manuelle, ajoutez une ligne dédiée.'
                )
