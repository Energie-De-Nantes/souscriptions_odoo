"""Fabrique unique du client electricore (#88/#77, ADR 0024).

Avant cet ADR, le service RSC (#88) et le wizard de pull des méta-périodes
(#77) portaient chacun leur propre garde d'import, leur propre drapeau de
disponibilité, leur propre lecture de config et leur propre `_client()` —
le tout copié à l'identique. Ce module concentre les quatre dans une unique
couture : un `AbstractModel` (`souscription.electricore.client`, méthode
publique `client()`) que les deux appelants utilisent via `self.env`, sans
jamais construire leur propre client.

Dépendance molle (#77 AC1) : `electricore-client` reste épinglé dans
requirements.txt et gardé par un `try/import`, mais n'est **jamais** déclaré
en `external_dependencies` — son absence n'empêche ni l'installation ni le
chargement du module, seul l'appel à `client()` échoue, avec un message
actionnable.

Chaque appelant garde son propre appel d'endpoint (`resoudre_rsc` en lot ↔
`meta_periodes` en flux) et son propre mapping d'exceptions : cette fabrique
s'arrête à « rends-moi un client configuré » (ADR 0024 §4, option écartée
« fabrique de transport complète »).
"""

from __future__ import annotations

from odoo import models
from odoo.exceptions import UserError

try:
    from electricore_client import ElectricoreClient

    ELECTRICORE_CLIENT_DISPONIBLE = True
except ImportError:  # pragma: no cover - exercé par test_electricore_client_fabrique
    ELECTRICORE_CLIENT_DISPONIBLE = False


class SouscriptionElectricoreClient(models.AbstractModel):
    _name = 'souscription.electricore.client'
    _description = 'Fabrique unique du client electricore (ADR 0024)'

    def client(self):
        """Construit un client electricore configuré.

        Acquis en tête de chaque action appelante (échec rapide et
        déterministe, ADR 0024 §5) : la construction n'ouvre aucune socket,
        seule l'ouverture du flux / l'appel batch parle réseau.

        Raises:
            UserError: le paquet `electricore_client` est absent (fait de
                démarrage), ou la configuration système est manquante
                (donnée runtime, éditable à chaud).
        """
        if not ELECTRICORE_CLIENT_DISPONIBLE:
            raise UserError(
                "Le paquet 'electricore_client' n'est pas installé sur ce serveur. "
                'Installez la dépendance épinglée dans requirements.txt puis réessayez.'
            )
        ICP = self.env['ir.config_parameter'].sudo()
        url = ICP.get_param('souscriptions.electricore_url')
        api_key = ICP.get_param('souscriptions.electricore_api_key')
        if not url or not api_key:
            raise UserError(
                'Configuration electricore manquante : renseignez les paramètres système '
                "'souscriptions.electricore_url' et 'souscriptions.electricore_api_key'."
            )
        return ElectricoreClient(url=url, api_key=api_key)
