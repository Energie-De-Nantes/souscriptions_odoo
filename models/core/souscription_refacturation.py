import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Garde d'import minimale (ADR 0024) : seules les exceptions du mapping de ce
# module sont importées ici — la construction du client (garde + drapeau +
# config) vit dans la fabrique. Si le paquet est absent, la fabrique lève
# avant qu'aucune de ces exceptions ne puisse être levée.
try:
    from electricore_client import ContractVersionError, IngestionEnCours
    from electricore_client.exceptions import PreconditionNonRemplie
except ImportError:  # pragma: no cover - paquet optionnel ; la fabrique lève avant tout mapping

    class ContractVersionError(Exception):
        """Repli si `electricore_client` est absent : jamais levée en pratique."""

    class IngestionEnCours(Exception):
        """Repli si `electricore_client` est absent : jamais levée en pratique."""

    class PreconditionNonRemplie(Exception):
        """Repli si `electricore_client` est absent : jamais levée en pratique."""


_logger = logging.getLogger(__name__)


class SouscriptionRefacturation(models.Model):
    """Refacturation Enedis (#8 / ADR 0009 ; renommée #38 — cf. CONTEXT.md).

    En-cours refacturable d'origine Enedis que le fournisseur refacture au·à la
    souscripteur·rice. Deux *natures* (prestation taxée / indemnité hors champ TVA)
    qui, avec le tarif solidaire, choisissent le *Produit de facturation* (ADR 0013).
    Indépendante de la Période : `facture_id` NULL = file « à refacturer » ; il est
    posé quand une Facture la rassemble (lien côté refacturation, ADR 0004).
    """

    _name = 'souscription.refacturation'
    _description = 'Refacturation Enedis'

    souscription_id = fields.Many2one(
        'souscription.souscription', required=True, ondelete='cascade', string='Souscription'
    )
    pdl = fields.Char(string='PDL')
    reference = fields.Char(string='Référence (electricore)', required=True)
    code_enedis = fields.Char(string='Code Enedis')
    libelle = fields.Char(string='Libellé', required=True)
    prix = fields.Float(string='Prix (€)', help='Prix de refacturation ; peut être négatif (avoir/pénalité).')
    quantite = fields.Float(string='Quantité', default=1.0)

    # Régime de TVA porté par la *nature*, pas par un taux par presta (ADR 0009 §5).
    # La nature choisit le produit de refacturation ; la TVA suit le produit
    # (configuré par le·la comptable), jamais un override de ligne — on ne
    # contourne donc pas les positions fiscales. Les `indemnité` (pénalités de
    # coupure dues par Enedis) sont hors champ TVA. Alimenté par le sync F15 (#37).
    nature = fields.Selection(
        [
            ('prestation', 'Prestation (TVA)'),
            ('indemnite', 'Indemnité (sans TVA)'),
        ],
        string='Nature',
        default='prestation',
        required=True,
    )

    # Mise en attente manuelle par le·la facturiste sur un doute (ADR 0012) :
    # opt-out de la facturation automatique. Tant que coché et non facturée, la
    # prestation est exclue de creer_factures() (cf. _facturer_refacturations).
    en_attente = fields.Boolean(string='En attente', default=False)

    # État dérivé pour le groupage/les stats de l'écran de vérification (ADR 0012).
    # L'ordre des valeurs pilote l'ordre des groupes. `facture_id` prime : il reste
    # l'unique source de vérité du « facturé » (ADR 0009 §4) ; `etat` ne fait que la
    # projeter. Stocké pour pouvoir grouper/filtrer/agréger côté SQL.
    etat = fields.Selection(
        [
            ('a_refacturer', 'À refacturer'),
            ('en_attente', 'En attente'),
            ('facturee', 'Facturée'),
            ('emise', 'Émise'),
        ],
        string='État',
        compute='_compute_etat',
        store=True,
    )

    @api.depends('facture_id', 'facture_id.state', 'en_attente')
    def _compute_etat(self):
        for presta in self:
            if presta.facture_id:
                presta.etat = 'emise' if presta.facture_id.state == 'posted' else 'facturee'
            elif presta.en_attente:
                presta.etat = 'en_attente'
            else:
                presta.etat = 'a_refacturer'

    # Marqueur « facturé » et unique lien Période-libre ↔ Facture : posé quand la
    # prestation est rassemblée sur une facture (ADR 0004, lien côté « plusieurs »).
    # `set null` : supprimer la facture re-met la prestation dans la file.
    facture_id = fields.Many2one('account.move', string='Facture', readonly=True, ondelete='set null', copy=False)

    # Clé de dédup du sync electricore (ADR 0009) : une prestation = une référence
    # de contenu fabriquée par electricore (contrat `prestations` v1 — le F15 n'a
    # pas d'identifiant de ligne). Pull-tout-et-dédup s'appuie dessus pour rester
    # idempotent.
    _unique_reference = models.Constraint(
        'UNIQUE(reference)',
        'Une prestation existe déjà pour cette référence.',
    )

    # --- Sync electricore : pull-tout des prestations F15 (#147, ADR 0009 §2 amendé) ---

    def synchroniser_depuis_electricore(self):
        """Tire TOUTES les prestations F15 d'electricore, insert-si-absente par `reference`.

        Pas de fenêtre temporelle : les lignes F15 arrivent en retard, datées dans
        le passé — un curseur de date les manquerait (ADR 0009 §2) ; l'idempotence
        vient de l'insert-si-absente sur la *Référence de contenu* (même référence
        = même contenu par construction, cf. CONTEXT.md) — aucun chemin d'update,
        le gel des facturées (ADR 0009 §4) est donc automatique. Le client est
        acquis en tête, avant tout travail (échec rapide et déterministe, ADR 0024 §5).
        """
        client = self.env['souscription.electricore.client'].client()
        try:
            lignes = self._tirer_prestations(client)
        except IngestionEnCours:
            raise UserError(_("L'ingestion electricore est en cours (verrou base) : réessayez plus tard."))
        except PreconditionNonRemplie as exc:
            raise UserError(_('Précondition non remplie côté electricore : %s', exc))
        except ContractVersionError as exc:
            raise UserError(_('Contrat electricore obsolète : %s', exc))
        compte = self._inserer_prestations(lignes)
        message = _(
            'Prestations : %(creees)s créée(s), %(ignorees)s sans souscription (RSC inconnue), '
            '%(erreurs)s en erreur (voir logs).',
            **compte,
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sync prestations electricore'),
                'message': message,
                'type': 'warning' if compte['erreurs'] or compte['ignorees'] else 'success',
                'sticky': False,
            },
        }

    def _tirer_prestations(self, client):
        """Couture transport (patchée par les tests) : consomme le flux JSONL typé
        (`PrestationF15`, contrat v1) et rend des dicts plats. Seul endroit qui
        parle réseau."""
        with client.prestations() as flux:
            return [presta.model_dump() for presta in flux]

    def _inserer_prestations(self, lignes):
        """Insert-si-absente par `reference`, résolution par RSC seule.

        Résolution par RSC, sans repli PDL (ADR 0010 §4 : aucun repli flou sur le
        flux vif) : une RSC qui ne matche aucune *Souscription* est ignorée et
        comptée — signal de backfill RSC, la ligne est rattrapée gratuitement au
        run suivant. Une référence déjà présente n'est jamais touchée (pas de
        chemin d'update). Savepoint par ligne (skip-and-report, ADR 0011) : une
        contrainte sur une ligne n'emporte pas le lot.
        """
        existantes = set(
            self.search([('reference', 'in', [ligne['reference'] for ligne in lignes])]).mapped('reference')
        )
        rscs = {ligne['ref_situation_contractuelle'] for ligne in lignes if ligne.get('ref_situation_contractuelle')}
        par_rsc = {
            s.ref_situation_contractuelle: s
            for s in self.env['souscription.souscription'].search([('ref_situation_contractuelle', 'in', list(rscs))])
        }
        compte = {'creees': 0, 'ignorees': 0, 'erreurs': 0}
        for ligne in lignes:
            if ligne['reference'] in existantes:
                continue
            souscription = par_rsc.get(ligne.get('ref_situation_contractuelle'))
            if souscription is None:
                compte['ignorees'] += 1
                continue
            try:
                with self.env.cr.savepoint():
                    self.create(self._vals_prestation(ligne, souscription))
                compte['creees'] += 1
            except Exception:
                _logger.warning('Sync prestation %s : échec, ligne sautée.', ligne.get('reference'), exc_info=True)
                compte['erreurs'] += 1
        return compte

    @api.model
    def _vals_prestation(self, ligne, souscription):
        # On ne classe 'prestation' (taxée) QUE sur un taux numérique explicite.
        # 'NS', null, vide ou toute valeur non numérique -> 'indemnite' (hors champ
        # TVA, pénalité due par Enedis). Le fail-safe est fiscal : sans lui, un taux
        # null — vu sur des DCOUP_PEN de l'API prestations — retombait sur 'prestation'
        # et facturait de la TVA sur une pénalité qui n'en porte pas. La TVA elle-même
        # suit le PRODUIT choisi par la nature (ADR 0009 §5) — jamais ce taux.
        # `montant_ht` est ignoré : prix × quantité fait foi (vérifié en spike,
        # 0 écart sur toutes les lignes UNITE).
        taux = (ligne.get('taux_tva_applicable') or '').strip().replace(',', '.')
        try:
            taxee = float(taux) > 0
        except ValueError:
            taxee = False
        return {
            'reference': ligne['reference'],
            'souscription_id': souscription.id,
            'pdl': ligne.get('pdl') or False,
            'code_enedis': ligne.get('id_ev') or False,
            'libelle': ligne.get('libelle_ev') or ligne.get('id_ev') or 'Prestation Enedis',
            'prix': ligne.get('prix_unitaire') or 0.0,
            'quantite': ligne.get('quantite') or 1.0,
            'nature': 'prestation' if taxee else 'indemnite',
        }

    def _composer_ligne(self):
        """Compose la ligne de facture (`(0, 0, vals)`) de cette prestation.

        Le produit de refacturation vient du catalogue (`souscription.produit`),
        choisi par la *nature* et le *tarif solidaire* de la souscription : il
        porte le compte + la TVA (ADR 0009 §5, ADR 0013). La ligne ne surcharge
        que libellé/prix/quantité. Ne crée aucun `account.move`.
        """
        self.ensure_one()
        produit = self.env['souscription.produit'].produit_refacturation(
            self.nature, self.souscription_id.tarif_solidaire
        )
        return (
            0,
            0,
            {
                'product_id': produit.id,
                'name': self.libelle,
                'quantity': self.quantite,
                'price_unit': self.prix,
            },
        )
