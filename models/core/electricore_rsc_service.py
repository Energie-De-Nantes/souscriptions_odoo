"""Service transport unique vers l'endpoint de résolution RSC d'electricore
(#88, ADR 0021 §3, contrat figé `docs/contrat-rsc.md` côté electricore).

Le client electricore est acquis auprès de la fabrique unique
`souscription.electricore.client` (ADR 0024) : ce module ne porte plus ni
garde d'import, ni drapeau de disponibilité, ni lecture de config — seul son
propre appel d'endpoint (`resoudre_rsc` en lot) et son mapping d'exception
(`ContractVersionError`, ré-exportée par la fabrique — #222).

C'est l'unique point du module qui parle réseau pour la résolution RSC ; le
pull des périodes (#12) s'y branchera plus tard.
"""

from __future__ import annotations

from odoo import models
from odoo.exceptions import UserError

from .electricore_client_fabrique import ContractVersionError


class SouscriptionRscService(models.AbstractModel):
    _name = 'souscription.rsc.service'
    _description = 'Résolution RSC electricore (id_Affaire -> ref_situation_contractuelle)'

    def resoudre(self, ids):
        """Résout un lot d'`id_affaire` en RSC/motif d'erreur — un appel
        batch, même pour un seul `id_affaire`.

        Args:
            ids: liste d'`id_affaire` à résoudre. Lot vide -> pas d'appel.

        Returns:
            dict[str, ResultatResolutionRsc] : un résultat par id_affaire,
            apparié **par id_affaire** (jamais par position), tolérant au
            désordre de la réponse.

        Raises:
            UserError: paquet absent, configuration manquante (fabrique,
                ADR 0024), ou version de contrat inattendue — dans tous les
                cas, aucune donnée n'est écrite par l'appelant puisque
                l'exception interrompt l'appel avant tout accès au résultat.
        """
        ids = list(ids)
        if not ids:
            return {}
        try:
            resultats = self._appeler(ids)
        except ContractVersionError as exc:
            raise UserError(f'Contrat electricore obsolète : {exc}') from exc
        return {r.id_affaire: r for r in resultats}

    def _appeler(self, ids):
        """Point de transport unique : acquiert le client via la fabrique
        (`souscription.electricore.client`, ADR 0024) et appelle
        `resoudre_rsc`. Seul endroit qui parle réseau — c'est la couture
        patchée en tests (réponses en boîte, rien d'autre n'est mocké)."""
        return self.env['souscription.electricore.client'].client().resoudre_rsc(ids)
