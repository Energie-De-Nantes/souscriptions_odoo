"""Tests de la fabrique unique de client electricore (#88/#77, ADR 0024).

Teste **une seule fois** la garde partagée par le service RSC (#88) et le
wizard de pull des méta-périodes (#77) : paquet absent, configuration
manquante, construction. Ces deux appelants ne testent plus que leur propre
couture de transport (`_appeler` / `_ouvrir_flux`), plus jamais cette garde
(cf. tests/test_rsc_service.py, tests/test_pull_meta_periodes.py).
"""

import os
from unittest.mock import patch

from odoo.addons.souscriptions_odoo.models.core import electricore_client_fabrique as fabrique_module
from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .common import SouscriptionsTestCase

_MODEL = 'souscription.electricore.client'


@tagged('souscriptions', 'souscriptions_electricore_client_fabrique', 'post_install', '-at_install')
class TestElectricoreClientFabrique(SouscriptionsTestCase):
    def setUp(self):
        super().setUp()
        patcher = patch.object(fabrique_module, 'ELECTRICORE_CLIENT_DISPONIBLE', True)
        patcher.start()
        self.addCleanup(patcher.stop)
        # #152 : la fabrique retombe sur les variables d'environnement
        # ELECTRICORE_URL/API_KEY quand l'ir.config_parameter est absent. On les
        # neutralise ici pour rendre ces tests hermétiques (config = config_parameter
        # seul) — sinon un .env local (ELECTRICORE_* réels, monté par docker-compose)
        # fait passer le repli et les cas « config absente → UserError » échouent en
        # local (verts en CI, où l'env est vide).
        env_patcher = patch.dict(os.environ, {'ELECTRICORE_URL': '', 'ELECTRICORE_API_KEY': ''})
        env_patcher.start()
        self.addCleanup(env_patcher.stop)
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('souscriptions.electricore_url', 'https://electricore.example.test')
        ICP.set_param('souscriptions.electricore_api_key', 'fake-api-key')

    def test_paquet_manquant_leve_userror_actionnable(self):
        with patch.object(fabrique_module, 'ELECTRICORE_CLIENT_DISPONIBLE', False):
            with self.assertRaises(UserError) as cm:
                self.env[_MODEL].client()
        self.assertIn('electricore_client', str(cm.exception))

    def test_url_manquante_leve_userror(self):
        self.env['ir.config_parameter'].sudo().set_param('souscriptions.electricore_url', False)
        with self.assertRaises(UserError):
            self.env[_MODEL].client()

    def test_api_key_manquante_leve_userror(self):
        self.env['ir.config_parameter'].sudo().set_param('souscriptions.electricore_api_key', False)
        with self.assertRaises(UserError):
            self.env[_MODEL].client()

    def test_construit_le_client_configure(self):
        """La fabrique construit bien `ElectricoreClient` avec la config lue
        (`ir.config_parameter`), sans autre traduction."""
        with patch.object(fabrique_module, 'ElectricoreClient') as MockClient:
            self.env[_MODEL].client()
        MockClient.assert_called_once_with(url='https://electricore.example.test', api_key='fake-api-key')
