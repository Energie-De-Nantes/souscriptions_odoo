"""Test structurel du catalogue de la Campagne (#342, ADR 0036 décision 12 —
le « grand A », PRD #339).

`ETAPES_CAMPAGNE` est devenu l'interface complète du DAG : chaque entrée
déclare tout ce qu'est son étape en clés plates, méthodes nommées par chaîne.
Ce test la verrouille comme contrat, pas comme scénario : chaque prérequis
référence une étape existante, l'ordre d'insertion est topologique, chaque
méthode nommée existe sur son modèle (`getattr`), toute clé inconnue est
refusée — la classe de bug « étape bloquée à vie sur une faute de frappe, en
silence » (ADR 0036) meurt ici. Aucune couture réseau, aucun scénario métier :
`self.env[modele]` sert de seul registre pour vérifier qu'une méthode existe
bien SUR SON MODÈLE (aucun enregistrement créé, sauf le test de non-régression
`phase` en fin de fichier)."""

from datetime import date
from unittest.mock import patch

from odoo.addons.souscriptions_odoo.models.core import souscription_campagne as campagne_module
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

ETAPES_CAMPAGNE = campagne_module.ETAPES_CAMPAGNE
CLES_CATALOGUE_CONNUES = campagne_module.CLES_CATALOGUE_CONNUES

_MODELE_CAMPAGNE = 'souscription.campagne.facturation'
_MODELE_ETAPE = 'souscription.campagne.etape'

# Modèle sur lequel chaque clé plate du catalogue nomme une méthode —
# connaissance de CE test, pas du catalogue (qui reste muet là-dessus : il ne
# porte qu'un nom de méthode, jamais son modèle). `action`/`reste_a_faire`/
# `amorcage` sont dispatchées via `getattr(self.campagne_id, methode)`
# (Campagne) ; `drill_down` via `getattr(self, methode)` où `self` est la
# ligne d'étape (Etape).
_MODELE_PAR_CLE = {
    'action': _MODELE_CAMPAGNE,
    'drill_down': _MODELE_ETAPE,
    'reste_a_faire': _MODELE_CAMPAGNE,
    'amorcage': _MODELE_CAMPAGNE,
}

# `vidange.liste_travail`/`vidange.ok` vivent sur la Campagne ; `vidange.action`
# est appelée sur le recordset RENDU par `liste_travail` (souscriptions pour
# « créer factures », factures pour « émettre factures ») — seul endroit où
# le modèle n'est pas uniforme d'une entrée à l'autre, câblé ici en dur.
_MODELE_VIDANGE_ACTION = {
    'creer_factures': 'souscription.souscription',
    'emettre_factures': 'account.move',
}


@tagged('souscriptions', 'souscriptions_campagne', 'post_install', '-at_install')
class TestCatalogueCampagneStructurel(TransactionCase):
    def test_toute_cle_inconnue_est_refusee(self):
        for code, info in ETAPES_CAMPAGNE.items():
            inconnues = set(info) - CLES_CATALOGUE_CONNUES
            self.assertFalse(inconnues, f'{code} : clé(s) inconnue(s) au catalogue {inconnues}')

    def test_chaque_prerequis_reference_une_etape_existante(self):
        for code, info in ETAPES_CAMPAGNE.items():
            for prereq in info.get('prerequis', ()):
                self.assertIn(prereq, ETAPES_CAMPAGNE, f'{code} : prérequis inconnu {prereq!r}')

    def test_ordre_dinsertion_est_topologique(self):
        """Chaque étape n'apparaît qu'après TOUS ses prérequis — l'ordre du
        dict EST un ordre topologique valide du DAG (source de vérité de
        l'ordre d'affichage/seed, ADR 0025 §1)."""
        vus = set()
        for code, info in ETAPES_CAMPAGNE.items():
            for prereq in info.get('prerequis', ()):
                self.assertIn(prereq, vus, f'{code} : prérequis {prereq!r} pas encore vu (ordre non topologique)')
            vus.add(code)

    def test_type_est_une_valeur_connue(self):
        for code, info in ETAPES_CAMPAGNE.items():
            self.assertIn(info.get('type'), ('porte', 'derive', 'action'), f'{code} : type inconnu')

    def test_phase_est_une_des_quatre_valeurs_du_prd(self):
        """#342, ADR 0036 décision 14 : tirer / verifier / facturer / solder."""
        for code, info in ETAPES_CAMPAGNE.items():
            self.assertIn(info.get('phase'), ('tirer', 'verifier', 'facturer', 'solder'), f'{code} : phase inconnue')

    def test_gate_absente_ou_dure_jamais_douce_explicite(self):
        """#342, ADR 0036 décision 11 : la dureté déclarée ne porte qu'une
        valeur, 'dure' — l'absence de clé EST la valeur 'douce' par défaut
        (clé absente = défaut, jamais une chaîne 'douce' redondante)."""
        for code, info in ETAPES_CAMPAGNE.items():
            if 'gate' in info:
                self.assertEqual(info['gate'], 'dure', f"{code} : 'gate' ne devrait valoir que 'dure'")

    def test_toute_entree_non_porte_declare_une_action(self):
        """Review #350 : une étape 'action'/'derive' sans clé `action` ne
        surfacerait qu'en UserError au clic du bouton générique — la même
        classe « typo silencieux » que ce fichier existe pour tuer. Une porte
        n'a jamais d'action (elle se valide via `valide`)."""
        for code, info in ETAPES_CAMPAGNE.items():
            if info.get('type') != 'porte':
                self.assertIn('action', info, f'{code} : entrée non-porte sans action')

    def test_toute_gate_dure_est_reellement_appliquee(self):
        """Review #350 : lie la déclaration `gate: 'dure'` à son enforcement
        (les appels `_verifier_gate` dans les méthodes d'action) — sinon les
        deux dérivent en silence. Paramétrique sur le catalogue : toute future
        entrée dure (p. ex. #314) est couverte à sa création. Le sens inverse
        (appel sans déclaration) est un assert dans `_verifier_gate` même.

        Le blocage est FORCÉ en patchant le compute `etat_prerequis` (le seam
        exact que `_verifier_gate` lit) : sur une campagne vierge sans données,
        les étapes dérivées sont vacuement « faites » (reste-à-faire 0) et
        certaines gates naîtraient prêtes — le scénario resterait couplé aux
        fixtures au lieu du catalogue."""

        def _tout_bloquer(etapes):
            for etape in etapes:
                etape.etat_prerequis = 'bloquee'

        campagne = self.env['souscription.campagne.facturation'].create({'mois': date(2024, 4, 1)})
        with patch.object(self.registry[_MODELE_ETAPE], '_compute_etat_prerequis', _tout_bloquer):
            campagne.etape_ids.invalidate_recordset(['etat_prerequis'])
            for code, info in ETAPES_CAMPAGNE.items():
                if info.get('gate') != 'dure':
                    continue
                self.assertIn('action', info, f'{code} : gate dure sans action à garder')
                with self.assertRaises(UserError, msg=f'{code} : gate déclarée dure mais action non gardée'):
                    getattr(campagne, info['action'])()

    def test_type_derive_porte_toujours_une_cible_statut_ou_un_reste_a_faire(self):
        """Toute étape 'derive' doit déclarer `cible_statut` OU `reste_a_faire`
        (générique `_compute_fait`/`_compute_nb_reste_a_faire`, #342) — sinon
        son reste-à-faire retomberait silencieusement à 0 pour toujours.
        `reste_a_faire` seul (#314, `envoyer_factures`) : son signal
        (`is_move_sent`) n'a pas de palier dans `_STATUTS_ORDONNES`
        (qui s'arrête à « émise »), même raison que `preparer_prelevements`
        (type 'action', déjà `reste_a_faire` seul)."""
        for code, info in ETAPES_CAMPAGNE.items():
            if info.get('type') == 'derive':
                self.assertTrue(
                    'cible_statut' in info or 'reste_a_faire' in info,
                    f'{code} : type derive sans cible_statut ni reste_a_faire',
                )

    def test_les_methodes_plates_existent_sur_leur_modele(self):
        for code, info in ETAPES_CAMPAGNE.items():
            for cle, modele in _MODELE_PAR_CLE.items():
                methode = info.get(cle)
                if not methode:
                    continue
                self.assertTrue(
                    hasattr(self.env[modele], methode),
                    f'{code}.{cle} : {modele!r} ne porte pas de méthode {methode!r}',
                )

    def test_les_methodes_de_vidange_existent_sur_leur_modele(self):
        for code, info in ETAPES_CAMPAGNE.items():
            vidange = info.get('vidange')
            if not vidange:
                continue
            for cle in ('liste_travail', 'ok'):
                methode = vidange[cle]
                self.assertTrue(
                    hasattr(self.env[_MODELE_CAMPAGNE], methode),
                    f'{code}.vidange.{cle} : Campagne ne porte pas de méthode {methode!r}',
                )
            modele_action = _MODELE_VIDANGE_ACTION[code]
            self.assertTrue(
                hasattr(self.env[modele_action], vidange['action']),
                f'{code}.vidange.action : {modele_action!r} ne porte pas de méthode {vidange["action"]!r}',
            )
            for cle in ('message_echec', 'libelle_reussite'):
                self.assertIsInstance(vidange[cle], str, f'{code}.vidange.{cle} : devrait être une chaîne')

    def test_vidange_presente_seulement_sur_les_deux_etapes_en_tache_de_fond(self):
        codes_avec_vidange = {code for code, info in ETAPES_CAMPAGNE.items() if 'vidange' in info}
        self.assertEqual(codes_avec_vidange, {'creer_factures', 'emettre_factures'})

    def test_amorcage_present_seulement_sur_les_trois_pulls(self):
        """AC #343, ADR 0036 : la frontière machine/humain est structurelle —
        seuls les trois pulls (« tirer de la donnée ») portent la clé
        `amorcage` ; aucune porte, aucune étape de facturation/solde
        (« juger et engager comptablement ») n'est machine-runnable."""
        codes_avec_amorcage = {code for code, info in ETAPES_CAMPAGNE.items() if 'amorcage' in info}
        self.assertEqual(codes_avec_amorcage, {'pull_sorties_c15', 'pull_meta_periodes', 'sync_f15'})

    def test_creation_seme_les_etapes_avec_la_phase_du_catalogue(self):
        """Non-régression légère : le champ compute stocké `phase` (#342)
        est peuplé, cohérent avec le catalogue, sur les lignes réellement
        créées — la seule assertion de ce fichier qui touche l'ORM au-delà
        d'un `getattr`."""
        campagne = self.env['souscription.campagne.facturation'].create({'mois': date(2024, 3, 1)})
        for etape in campagne.etape_ids:
            self.assertEqual(etape.phase, ETAPES_CAMPAGNE[etape.code]['phase'])
