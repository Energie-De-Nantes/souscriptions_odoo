# Souscriptions Électriques pour Odoo

[![Tests](https://github.com/Energie-De-Nantes/souscriptions_odoo/actions/workflows/tests.yml/badge.svg)](https://github.com/Energie-De-Nantes/souscriptions_odoo/actions/workflows/tests.yml)

Un addon libre pour **Odoo 19** qui gère les contrats de fourniture d'électricité en France.
Créé par [Virgile Daugé](https://github.com/virgiledauge) pour
[Énergie de Nantes](https://github.com/Energie-De-Nantes), partagé sous licence **AGPL-3**
pour permettre l'émergence d'autres communs de l'électricité.

## Pourquoi ce projet existe ?

Parce que gérer un contrat d'électricité, c'est pas pareil que vendre des chaussettes !

Le module d'abonnement standard d'Odoo ne sait pas :

- changer les prix en cours de contrat (fluctuations du marché, des taxes…) ;
- facturer une régularisation aux **prix historiques** de chaque période ;
- gérer le **lissage mensuel** avec rattrapage ;
- parler le langage du métier : PDL, cadrans HP/HC, TURPE, flux Enedis…

Ce module remplace donc le système d'abonnement standard par un modèle qui comprend
vraiment la fourniture d'électricité : la **Souscription** (le contrat), ses **Périodes**
mensuelles de facturation, des **Grilles de prix** datées, la facture légale et le portail
usager.

## Architecture : Odoo + electricore

La responsabilité est volontairement coupée en deux :

- **[electricore](https://github.com/Energie-De-Nantes/electricore)** porte tout le savoir
  métier *réseau* : ingestion des flux Enedis, périmètre, énergies par cadran, TURPE,
  accise, CTA. Il est déployé avec une API REST.
- **Ce module Odoo** garde le rôle *fournisseur* : contrat, grilles de prix, facturation
  légale, comptabilité, paiements, portail client et workflow de raccordement. Il consomme
  l'API d'electricore (via le paquet [`electricore-client`](https://pypi.org/project/electricore-client/))
  pour alimenter ses périodes de facturation.

Le vocabulaire du domaine (Souscription, Période, Relevé, Grille de prix, Campagne de
facturation…) est défini dans [CONTEXT.md](CONTEXT.md) ; les décisions d'architecture sont
tracées dans [docs/adr/](docs/adr/).

## Fonctionnalités

L'état détaillé, capacité par capacité avec sa preuve (test + issue), est tenu dans la
story map [FEATURES.md](FEATURES.md). En résumé, par parcours :

**Raccordement (l'entrée)** — un kanban piloté par les faits, conduit par l'accueilliste :
routage particulier/pro, validation IBAN/SIRET, création de la Souscription à
l'acceptation, suivi automatique des affaires Enedis (poll quotidien, résolution de la
RSC), mails de rassurage et pack de bienvenue avec conditions particulières en pièce
jointe.

**Contrat & documents** — souscriptions Base ou HP/HC, tarif solidaire (isolation
comptable complète), majoration PRO, estimation automatique des provisions, journal des
actes append-only (consentements RGPD, acceptation CGV), conditions particulières et
attestation de fourniture en PDF.

**Grilles de prix** — barèmes fournisseur datés et versionnés, sélectionnés par régime
(standard ou Moulin) et par date — ce qui permet de facturer une régularisation aux prix
de l'époque. Abonnement affine (base 3 kVA + coefficient par kVA), TURPE absorbé, moteur
de prix unique projeté par la facture comme par les conditions particulières.

**Cycle mensuel de facturation** — la Campagne de facturation, tableau de bord du
facturiste : pull des méta-périodes electricore (idempotent), sync des prestations F15 à
refacturer, périodes mensuelles figées à la facturation (snapshot + relevés d'index
justificatifs), composition des lignes (prorata, cadrans, pro, solidaire), imputation FIFO
des chèques énergie, facture d'énergie PDF sur template dédié.

**Portail usager** — accès sécurisé et cloisonné, historique de consommation et bloc
justificatif des relevés — uniquement sur les factures **émises**, un brouillon ne fuite
jamais.

**Reprise de l'existant** — backfill des périodes d'ouverture liées aux factures legacy,
champs d'atterrissage pour la migration (pilotée par le dépôt `souscriptions_migration`).

## Démarrage rapide

### Instance locale avec Docker (recommandé)

```bash
git clone https://github.com/Energie-De-Nantes/souscriptions_odoo.git
cd souscriptions_odoo
./scripts/dev.sh
# puis ouvrir http://localhost:8069   (identifiants : admin / admin)
```

Le script construit l'image (`docker/Dockerfile`, `electricore-client` inclus) et lance
Odoo 19 avec le hot reload (`--dev=reload,xml,qweb`) : une modification de vue ou de
rapport QWeb est visible sans reconstruire. Par défaut, mode **demo** : base
`souscriptions_demo` avec des données d'exemple, persistée entre deux lancements.

- `./scripts/dev.sh --reset` — repart d'une base vierge ;
- `./scripts/dev.sh --data=prod` — mode **prod local** : base `souscriptions_prodlocal`,
  sans données de démo, avec de vraies données synchronisées depuis electricore.

À explorer dans l'instance de démo :

- **Souscriptions** : contrats d'exemple (Base, HP/HC, solidaire, pro) ;
- **Souscriptions → Grilles de Prix** : le barème avec abonnement affine ;
- **Souscriptions → Facturation** : campagnes de facturation mensuelles ;
- **Raccordements** : le kanban de demandes à différentes étapes ;
- le **portail** sur `/my` : donner un accès portail à un contact de démo
  (Contacts → *Action → Accorder l'accès au portail*), puis se connecter avec ce compte.

### Installation manuelle

Prérequis : Odoo 19, PostgreSQL, et le paquet `electricore-client` (voir
`requirements.txt` — le module s'installe sans lui, seule l'action de pull le réclame).

```bash
createdb votre_base
odoo -d votre_base -i souscriptions_odoo
```

## Tests

La suite (TransactionCase + HttpCase) tourne sur `odoo:19` + PostgreSQL via Docker, sans
installation locale d'Odoo :

```bash
./scripts/run-tests.sh                    # toute la suite
TEST_TAGS=mon_tag ./scripts/run-tests.sh  # une sélection
```

Le script démarre PostgreSQL, installe le module, lance la suite, nettoie les conteneurs
et renvoie le bon code de sortie. Détails (commande manuelle, CI, dépannage) :
[tests/README.md](tests/README.md). La même suite tourne en CI à chaque push (badge en
haut).

## Structure du projet

```
souscriptions_odoo/
├── models/
│   ├── core/         # Souscription, périodes, grilles, campagne, chèque énergie,
│   │                 # refacturation, relevés, journal des actes, account.move
│   ├── raccordement/ # Workflow kanban des demandes de raccordement
│   └── wizard/       # Assistants (pull des méta-périodes electricore…)
├── controllers/      # Routes du portail usager
├── views/            # Vues Odoo (core, raccordement, wizard, portail)
├── reports/          # Facture d'énergie, conditions particulières, attestation (QWeb)
├── data/             # Configuration par défaut (produits, séquences, crons, mails)
├── demo/             # Données de démo
├── security/         # Groupes, droits d'accès, règles
├── tests/            # Suite de tests
├── scripts/          # dev.sh (instance locale), run-tests.sh
└── docker/           # Image et compose de développement
```

## Documentation

| Document | Contenu |
|---|---|
| [CONTEXT.md](CONTEXT.md) | Le vocabulaire du domaine — la référence des termes métier |
| [FEATURES.md](FEATURES.md) | Story map : chaque capacité avec statut et preuve |
| [COOKBOOK.md](COOKBOOK.md) | Les routines du dépôt : lancer l'instance, tester, inspecter les données |
| [docs/adr/](docs/adr/) | Les décisions d'architecture (ADR) |
| [AUDIT_REFONTE.md](AUDIT_REFONTE.md) | L'audit qui a guidé la refonte Odoo 19 |

## Compatibilité et dépendances

**Odoo 19** — modules requis : `base`, `mail`, `contacts`, `account`, `portal`.

**Dépendances Python** (hors framework) :

- `electricore-client` (épinglé dans `requirements.txt`) — client fin vers l'API
  electricore ; dépendance *molle* : son absence n'empêche pas l'installation du module ;
- `babel` — dates en français.
