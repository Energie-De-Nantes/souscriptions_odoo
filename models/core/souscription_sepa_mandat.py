"""Service SEPA mandat (#217, PRD #215 tranche 2/3, CONTEXT.md « Mandat de
prélèvement (SEPA) »).

Le pont mandat SEPA — création du mandat actif d'emblée, résolution du
journal SDD, construction pure des valeurs — vivait dans la demande de
raccordement (#187) ; il devient un service `AbstractModel` côté core : c'est
un souci **paiements** (préalable au Mode de paiement « prélèvement »), pas un
souci d'intake. Son futur second appelant, le changement de mode de paiement
post-naissance (PRD #183), n'a rien à voir avec le raccordement.

Le modèle de mandat (`sdd.mandate`) vit dans le module Enterprise « Direct
Debit » : absent en Community/CI, jamais dans les `depends` du manifeste
(décision PRD #183 — pas de dépendance à un module privé). Garde runtime sur
le *registre* de modèles au point d'entrée unique (`creer`) : même idiome que
la dépendance molle d'electricore-client (ADR 0024), mais sur le registre
plutôt que sur un import Python. La résolution du journal SDD et la
construction des valeurs sont internes : l'appelant n'a rien à en connaître.
"""

from odoo import fields, models
from odoo.exceptions import UserError


class SouscriptionSepaMandat(models.AbstractModel):
    _name = 'souscription.sepa.mandat'
    _description = "Service SEPA mandat — création active d'emblée (idiome registre, ADR 0024)"

    def creer(self, partner_bank, date_signature=None, rum=None):
        """Crée le mandat SEPA, actif d'emblée, pour le compte bancaire
        donné. Point d'entrée unique du service (#217) : l'appelant ne
        connaît ni la résolution du journal SDD ni la construction des
        valeurs — seulement ce triplet d'arguments.

        Args:
            partner_bank: `res.partner.bank` porteur du mandat (le
                partenaire est dérivé de `partner_bank.partner_id`).
            date_signature: date de signature du mandat, reprise telle
                quelle comme date de début ; défaut aujourd'hui si absente.
            rum: référence unique de mandat saisie ; défaut laissé à
                l'outillage (Enterprise) si absente.

        Returns:
            Le `sdd.mandate` créé, ou `None` si le modèle Enterprise est
            absent du registre (Community/CI) — no-op silencieux, le reste
            de l'appelant se déroule à l'identique.

        Raises:
            UserError: aucun ou plusieurs journaux comptables n'exposent la
                méthode de paiement SDD (résolution interne, jamais exposée
                à l'appelant).
        """
        if 'sdd.mandate' not in self.env:
            return None
        journal = self._resoudre_journal_sdd()
        vals = self._mandat_sepa_vals(partner_bank, journal, date_signature=date_signature, rum=rum)
        return self.env['sdd.mandate'].create(vals)

    def _resoudre_journal_sdd(self):
        """Résout dynamiquement le journal comptable portant la méthode de
        paiement SDD (prélèvement SEPA) — jamais configuré en dur (#187).
        Erreur explicite si aucun journal ne l'expose ou si plusieurs le
        font : pas de mandat silencieusement rattaché au mauvais journal."""
        journaux = self.env['account.journal'].search(
            [
                ('company_id', '=', self.env.company.id),
                ('inbound_payment_method_line_ids.code', '=', 'sdd'),
            ]
        )
        if not journaux:
            raise UserError(
                "Aucun journal comptable n'expose la méthode de paiement SDD (prélèvement SEPA) : "
                "configurez-en un dans l'outillage comptable avant de créer un mandat en prélèvement."
            )
        if len(journaux) > 1:
            raise UserError(
                'Plusieurs journaux comptables exposent la méthode de paiement SDD (prélèvement SEPA), '
                f'ambiguïté à résoudre avant création du mandat : {", ".join(journaux.mapped("name"))}.'
            )
        return journaux

    def _mandat_sepa_vals(self, partner_bank, journal, date_signature=None, rum=None):
        """Construction pure des valeurs du mandat SEPA (#187) — sans accès
        au registre ni à la base au-delà des recordsets passés : testable en
        CI Community sans le modèle Enterprise `sdd.mandate`.

        RUM = `rum` si fourni, sinon absent du dict pour laisser le défaut
        de l'outillage la générer. Date de début = `date_signature` si
        fournie, sinon aujourd'hui. Schéma CORE, actif d'emblée (la porte
        humaine — IBAN vérifié, mandat signé exigé — est en amont de l'appel,
        chez chaque appelant : acceptation du raccordement aujourd'hui,
        changement de mode de paiement post-naissance demain, PRD #183).

        Noms de champs confrontés au `sdd.mandate` réel de la prod
        Enterprise (via MCP, 2026-07-11) : `payment_journal_id`,
        `sdd_scheme`, `state`, `partner_bank_id`, `start_date` confirmés ;
        `company_id` non requis. Omettre `name` (RUM) est le bon geste :
        l'action serveur prod créait ses ~1000 mandats sans le passer, le
        défaut de l'outillage le génère (un nom erroné lèverait au
        `create()`, jamais un mandat silencieusement faux).
        """
        vals = {
            'partner_id': partner_bank.partner_id.id,
            'partner_bank_id': partner_bank.id,
            'payment_journal_id': journal.id,
            'start_date': date_signature or fields.Date.context_today(self),
            'state': 'active',
            'sdd_scheme': 'CORE',
        }
        if rum:
            vals['name'] = rum
        return vals
