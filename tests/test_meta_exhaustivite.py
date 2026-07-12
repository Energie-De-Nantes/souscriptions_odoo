"""Méta-test d'exhaustivité (#221) : `tests/__init__.py` utilise des imports
explicites — un module `test_*.py` oublié de cette liste ne tourne jamais,
silencieusement (c'est ce qui a éteint test_periode_atterrissage,
test_periode_mois, test_invoice_template avant leur réanimation). Ce test
garde qu'un fichier présent dans le dossier ne peut plus s'éteindre sans
qu'un run de la suite échoue.
"""

import glob
import importlib
import os

from odoo.tests.common import TransactionCase, tagged

# Exclusions volontaires (fichier test_*.py présent mais délibérément non
# importé). Vide pour l'instant : tout module doit être dans __init__.py.
EXCLUSIONS = set()


@tagged('souscriptions', 'post_install', '-at_install')
class TestMetaExhaustiviteSuites(TransactionCase):
    def test_tous_les_modules_test_sont_importes(self):
        dossier = os.path.dirname(__file__)
        modules_presents = {
            os.path.splitext(os.path.basename(chemin))[0] for chemin in glob.glob(os.path.join(dossier, 'test_*.py'))
        }

        paquet = importlib.import_module(__package__)
        modules_importes = {nom for nom in vars(paquet) if nom.startswith('test_')}

        manquants = modules_presents - modules_importes - EXCLUSIONS
        self.assertFalse(
            manquants,
            f'Module(s) test_*.py absent(s) de tests/__init__.py (suite éteinte silencieusement) : {sorted(manquants)}',
        )
