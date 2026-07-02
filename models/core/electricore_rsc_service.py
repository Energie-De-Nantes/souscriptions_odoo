"""Service transport unique vers l'endpoint de résolution RSC d'electricore
(#88, ADR 0021 §3, contrat figé `docs/contrat-rsc.md` côté electricore).

Enveloppe le paquet PyPI épinglé `electricore-client` (requirements.txt),
même garde d'import et mêmes paramètres système que le wizard de pull des
méta-périodes (#84, `souscriptions.electricore_url` /
`souscriptions.electricore_api_key`) — dépendance déclarée par le pin +
la garde, pas par `external_dependencies` (cf. requirements.txt).

C'est l'unique point du module qui parle réseau pour la résolution RSC ; le
pull des périodes (#12) s'y branchera plus tard.
"""

from __future__ import annotations

from odoo import models
from odoo.exceptions import UserError

try:
    from electricore_client import ContractVersionError, ElectricoreClient

    ELECTRICORE_CLIENT_DISPONIBLE = True
except ImportError:  # pragma: no cover - exercé par test_paquet_manquant_leve_userror_actionnable
    ELECTRICORE_CLIENT_DISPONIBLE = False


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
            UserError: paquet absent, configuration manquante, ou version de
                contrat inattendue — dans tous les cas, aucune donnée n'est
                écrite par l'appelant puisque l'exception interrompt l'appel
                avant tout accès au résultat.
        """
        ids = list(ids)
        if not ids:
            return {}
        if not ELECTRICORE_CLIENT_DISPONIBLE:
            raise UserError(
                "Le paquet 'electricore_client' n'est pas installé sur ce serveur. "
                'Installez la dépendance épinglée dans requirements.txt puis réessayez.'
            )
        try:
            resultats = self._appeler(ids)
        except ContractVersionError as exc:
            raise UserError(f'Contrat electricore obsolète : {exc}') from exc
        return {r.id_affaire: r for r in resultats}

    def _appeler(self, ids):
        """Point de transport unique : construit le client et appelle
        `resoudre_rsc`. Seul endroit qui parle réseau — c'est la couture
        patchée en tests (réponses en boîte, rien d'autre n'est mocké)."""
        return self._client().resoudre_rsc(ids)

    def _client(self):
        """Client electricore depuis `ir.config_parameter` — mêmes clés que
        le wizard de pull des méta-périodes (#84)."""
        ICP = self.env['ir.config_parameter'].sudo()
        url = ICP.get_param('souscriptions.electricore_url')
        api_key = ICP.get_param('souscriptions.electricore_api_key')
        if not url or not api_key:
            raise UserError(
                'Configuration electricore manquante : renseignez les paramètres système '
                "'souscriptions.electricore_url' et 'souscriptions.electricore_api_key'."
            )
        return ElectricoreClient(url=url, api_key=api_key)
