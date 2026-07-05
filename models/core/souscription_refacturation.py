import logging

from odoo import _, api, fields, models

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
    reference_enedis = fields.Char(string='Référence Enedis', required=True)
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
    # Enedis. Pull-tout-et-dédup s'appuie dessus pour rester idempotent.
    _unique_reference_enedis = models.Constraint(
        'UNIQUE(reference_enedis)',
        'Une prestation existe déjà pour cette référence Enedis.',
    )

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

    # --- Sync electricore : pull-tout des prestations F15 (#37, ADR 0009 §2) ---

    def synchroniser_depuis_electricore(self):
        """Tire TOUTES les prestations F15 d'electricore et upsert par référence Enedis.

        Pas de fenêtre temporelle : les lignes F15 arrivent en retard, datées dans
        le passé — un curseur de date les manquerait (ADR 0009 §2) ; l'idempotence
        vient de la contrainte UNIQUE sur `reference_enedis`. Le client est acquis
        en tête, avant tout travail (échec rapide et déterministe, ADR 0024 §5).
        """
        client = self.env['souscription.electricore.client'].client()
        compte = self._upserter_prestations(self._tirer_prestations(client))
        message = _(
            'Prestations : %(creees)s créée(s), %(maj)s mise(s) à jour, %(facturees)s facturée(s) '
            'inchangée(s), %(ignorees)s sans souscription, %(erreurs)s en erreur (voir logs).',
            **compte,
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sync prestations electricore'),
                'message': message,
                'type': 'warning' if compte['erreurs'] else 'success',
                'sticky': False,
            },
        }

    def _tirer_prestations(self, client):
        """Couture transport (patchée par les tests) : consomme le flux JSONL typé
        (`PrestationF15`, contrat v1) et rend des dicts plats."""
        with client.prestations() as flux:
            return [presta.model_dump() for presta in flux]

    def _upserter_prestations(self, lignes):
        """Upsert par `reference_enedis` après résolution de la souscription.

        Savepoint par ligne (skip-and-report, ADR 0011) : une contrainte sur une
        ligne n'emporte pas le lot. Une prestation déjà FACTURÉE n'est jamais
        réécrite — `facture_id` est la source de vérité du « facturé » (ADR 0009
        §4), la refacturer suivrait la facture, pas le flux.
        """
        existantes = {
            p.reference_enedis: p
            for p in self.search([('reference_enedis', 'in', [ligne['reference'] for ligne in lignes])])
        }
        compte = {'creees': 0, 'maj': 0, 'facturees': 0, 'ignorees': 0, 'erreurs': 0}
        for ligne in lignes:
            souscription = self._resoudre_souscription(ligne)
            if not souscription:
                compte['ignorees'] += 1
                continue
            existante = existantes.get(ligne['reference'])
            if existante and existante.facture_id:
                compte['facturees'] += 1
                continue
            try:
                with self.env.cr.savepoint():
                    vals = self._vals_prestation(ligne, souscription)
                    if existante:
                        existante.write(vals)
                        compte['maj'] += 1
                    else:
                        self.create(vals)
                        compte['creees'] += 1
            except Exception:
                _logger.warning('Sync prestation %s : échec, ligne sautée.', ligne.get('reference'), exc_info=True)
                compte['erreurs'] += 1
        return compte

    def _resoudre_souscription(self, ligne):
        """RSC d'abord (une RSC identifie LE contrat — vrai même pour une prestation
        d'un ancien contrat sur le même PDL), PDL non résilié en repli et seulement
        s'il est sans ambiguïté. Sans résolution : recordset vide (ligne ignorée, v1)."""
        Souscription = self.env['souscription.souscription']
        rsc = ligne.get('ref_situation_contractuelle')
        if rsc:
            par_rsc = Souscription.search([('ref_situation_contractuelle', '=', rsc)], limit=1)
            if par_rsc:
                return par_rsc
        pdl = ligne.get('pdl')
        if pdl:
            candidates = Souscription.search([('pdl', '=', pdl), ('etat', '!=', 'resiliee')])
            if len(candidates) == 1:
                return candidates
        return Souscription.browse()

    @api.model
    def _vals_prestation(self, ligne, souscription):
        # 'NS' (non soumis) = indemnité hors champ TVA (pénalité due par Enedis) ;
        # tout taux numérique = prestation taxée. La TVA elle-même suit le PRODUIT
        # choisi par la nature (ADR 0009 §5) — jamais un taux recopié par ligne.
        non_soumis = (ligne.get('taux_tva_applicable') or '').strip().upper() == 'NS'
        return {
            'reference_enedis': ligne['reference'],
            'souscription_id': souscription.id,
            'pdl': ligne.get('pdl') or False,
            'code_enedis': ligne.get('id_ev') or False,
            'libelle': ligne.get('libelle_ev') or ligne.get('id_ev') or 'Prestation Enedis',
            'prix': ligne.get('prix_unitaire') or 0.0,
            'quantite': ligne.get('quantite') or 1.0,
            'nature': 'indemnite' if non_soumis else 'prestation',
        }
