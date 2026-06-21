# Consentement aux données de consommation — chaîne de responsabilité (RGPD / CNIL)

> Note de référence. Le glossaire ([CONTEXT.md](../CONTEXT.md)) définit le terme
> *Consentement (données de consommation)* ; la décision d'architecture est
> [ADR 0017](adr/0017-consentement-donnees-conso-formulaire-odoo-journal-append-only.md).
> Ce document n'est pas un avis juridique : faire valider le périmètre et les libellés par le·la DPO.

## Résumé (TL;DR)

1. **Il n'y a pas de signature.** Souscrire en ligne forme un contrat valide par simple échange des
   consentements (consensualisme). Le « Signé électroniquement le… » de prod est en réalité une
   **date de validation de formulaire**, pas une signature.
2. **Deux régimes à ne jamais confondre** : l'**acceptation contractuelle** (CGV / conditions
   particulières) et le **consentement RGPD** à la collecte de données. Ils ont des règles de
   preuve différentes.
3. **L'index suffit-il à facturer → pas de consentement** (exécution du contrat). Dès qu'on collecte
   **plus fin** (conso quotidienne transmise au fournisseur, courbe de charge) → **consentement RGPD
   obligatoire**, démontrable, versionné, révocable.
4. **EDN déclare à Enedis** détenir le consentement → **EDN porte la charge de la preuve**. D'où le
   choix d'un **journal append-only** co-localisé avec la *Souscription*, et d'un **formulaire de
   capture interne** (module raccordement) plutôt qu'externe.

---

## 1. La formation du contrat en ligne — sans signature

- **Consensualisme** (Code civil, art. 1172) : un contrat se forme par le seul échange des
  consentements ; la signature n'est **pas** une condition de validité (sauf contrats solennels).
  Souscrire par un clic forme donc un contrat valide.
- **Validité ≠ preuve.** Le clic forme le contrat ; le prouver ensuite relève d'un autre mécanisme.
- **Contrat électronique B2C** : le **« double clic »** (Code civil, art. 1127-2) — le·la
  consommateur·rice doit pouvoir **vérifier et corriger** sa commande puis la **confirmer** ; le
  professionnel en **accuse réception** par voie électronique.
- **Confirmation sur support durable** (Code de la conso., art. L221-13) : le fournisseur doit
  remettre la confirmation du contrat sur support durable, **avant le début d'exécution**, avec
  toutes les informations de l'art. L221-5.
- **Conséquence pour nous** : le **PDF des conditions particulières** est la **confirmation sur
  support durable**, pas un contrat signé. Sa valeur probante vient d'être cette confirmation **+**
  les **journaux** de la souscription (horodatage, version des CGV acceptée, double-clic), pas d'une
  signature.

## 2. Le consentement RGPD aux données de consommation

> **Repère** : « art. 6-1-a/b » renvoie au **RGPD** (Règlement (UE) 2016/679), **Article 6
> « Licéité du traitement », paragraphe 1**, qui liste les 6 bases légales (a→f) : a) consentement,
> b) exécution du contrat, c) obligation légale, d) intérêts vitaux, e) mission d'intérêt public,
> f) intérêts légitimes.

### Gradation Enedis (le cœur du sujet)

| Donnée | Base légale | Consentement ? |
|---|---|---|
| **Index** (relevé périodique) servant à **facturer** | Exécution du contrat (RGPD art. 6-1-b) | **Non** |
| **Consommations quotidiennes** transmises au **fournisseur** (au-delà du besoin de facturation) | Consentement (art. 6-1-a) | **Oui** |
| **Courbe de charge** (horaire / demi-horaire) | Consentement explicite | **Oui** |

Enedis : *« au-delà de ce qui est nécessaire à la facturation, aucune information n'est transmise à
un tiers sans le consentement libre, éclairé, spécifique et univoque du client »*. Pour la courbe de
charge, Enedis recueille soit le consentement du client (personne physique), soit une
**déclaration du fournisseur attestant qu'il détient ce consentement**. La transmission récurrente
peut être **interrompue à tout moment** sur simple demande (retrait).

### Conditions d'un consentement valable (RGPD art. 4-11 et 7)

- **Libre, spécifique, éclairé, univoque** — un **acte positif** (case **non** pré-cochée ; le
  silence ou une case déjà cochée ne valent pas consentement).
- **Spécifique = granulaire** : une finalité = un consentement (ne pas grouper « conso quotidienne »
  et « courbe de charge » en une seule case).
- **Démontrable** (*accountability*, art. 7-1) : le responsable doit pouvoir **prouver** que la
  personne a consenti.
- **Révocable** (art. 7-3) : le retrait doit être **aussi simple** que le consentement.

### Éléments à journaliser pour la preuve

Qui (identifiant unique) · Quelle **finalité** précise · **Quand** (horodatage) · **Comment**
(case à cocher / formulaire) · **Quelle version du texte** affichée (capture ou empreinte datée) ·
**Retrait** (possibilité + date effective). Un **booléen** ne suffit pas : il perd le quand, la
version et l'historique de retrait.

## 3. La chaîne de responsabilité (rôles RGPD)

- **Souscripteur·rice** — *personne concernée*.
- **EDN** — *responsable de traitement* (controller) : c'est son contrat, ses finalités.
- **Formulaire public** (module *raccordement*, Odoo) — **point de capture de l'acte positif**, sous
  le contrôle d'EDN (pas de sous-traitant externe).
- **`souscription.souscription` + journal `souscription.consentement`** — système de référence et
  **lieu de la preuve**.
- **electricore** — service d'EDN qui **exécute** la collecte consentie (pull Enedis).
- **Enedis (GRD)** — *tiers*, responsable de traitement **distinct** ; **source** des données et
  **destinataire de la déclaration de consentement** d'EDN.
- **CNIL** — autorité de contrôle (cible de l'*accountability*), **hors** flux de données.

### Les deux fils, de bout en bout

**A. Formation du contrat** : formulaire (offre : CGV + CP + tarifs) → double-clic (vérifier /
corriger / confirmer) → accusé de réception → `date_validation` enregistrée → **confirmation sur
support durable** (PDF CP) avant le début de fourniture. *Preuve = journaux du formulaire +
confirmation. Pas de signature.*

**B. Consentement données de consommation** : acte positif granulaire sur le formulaire (cases non
pré-cochées, texte versionné) → **ligne dans `souscription.consentement`** (finalité, horodatage,
version, source, état=donné) → EDN **déclare le consentement à Enedis** et demande l'activation
(via electricore / SGE) → Enedis collecte / transmet, electricore pull → **retrait** : nouvelle
ligne (état=retiré, date_retrait) → EDN demande la **désactivation** à Enedis. *Preuve = le journal
append-only + la version du texte.*

## 4. Pourquoi internaliser le formulaire (vs prod : externe → LSD)

LSD = *Liste des Souscriptions Différées*, un **module Odoo** (équivalent prod du *raccordement*). Le
seul maillon **externe** de la prod est donc le **formulaire**. Internaliser ce formulaire dans le
*raccordement* :

| Dimension | Externe → LSD (prod) | Formulaire Odoo interne (cible) |
|---|---|---|
| Point de capture de l'acte | Hors Odoo | Odoo, possédé par EDN |
| Où vit la preuve | Système du formulaire ; Odoo ne reçoit qu'un digest | **Avec le système de référence** |
| Intégrité texte ↔ preuve | PDF = texte statique rendu par un **autre** système → divergence | Texte affiché = consentement stocké = PDF, **source versionnée unique** |
| Rôles | Maillon externe (sous-traitant si tiers) | **Un seul responsable**, pas de sous-traitant |
| Retrait & droits | Éclatés | Un seul système |

**Condition impérative** : le formulaire doit être **public** (l'acte est celui du·de la
souscripteur·rice). Un formulaire back-office rempli par un·e facturiste **ne produit pas** de
consentement valable.

## 5. Modèle de données — journal de consentement append-only

`souscription.consentement` (immuable, une ligne par événement) :

| Champ | Rôle |
|---|---|
| `souscription_id` | rattachement (identifiant unique de la personne via le contrat) |
| `finalite` | ex. `donnees_quotidiennes`, `courbe_de_charge` (granulaire) |
| `date` | horodatage de l'acte |
| `version_texte` | référence/empreinte du libellé affiché |
| `source`, `ip` | preuve du canal (formulaire public) |
| `etat` | `donne` \| `retire` |
| `date_retrait` | effectivité du retrait (art. 7-3) |

État courant d'une finalité = **dernière ligne**. Le retrait **ajoute** une ligne ; rien n'est écrasé.

## 6. Conservation

Conserver la **preuve du consentement** le temps nécessaire pour la démontrer : durée du contrat +
délai de prescription des actions (en pratique ~5 ans pour les actions contractuelles ;
recommandation CNIL de conserver la preuve du consentement quelques années après son retrait / la
fin de la relation). À fixer avec le·la DPO.

## 7. Hors périmètre de ce module (chantiers distincts)

- Le **formulaire public** de souscription (website/portal Odoo) qui écrit le journal.
- L'**activation / désactivation** de la collecte chez Enedis (via electricore / SGE).
- L'**UI de retrait** au portail (art. 7-3 : aussi simple que donner).

## Sources

- [Consensualisme en droit français — Wikipédia](https://fr.wikipedia.org/wiki/Consensualisme_en_droit_fran%C3%A7ais)
- [Code civil, art. 1127-2 (contrat électronique, « double clic ») — Légifrance](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000032007506)
- [Preuve du contrat électronique B2C (double-clic, support durable L221-13) — Saint-Louis Recouvrement](https://www.saint-louis-recouvrement.com/preuve-contrat-electronique/)
- [« Le clic équivaut à une signature » — CGV-Expert](https://www.cgv-expert.fr/prestation-redaction-conditions-generales/validation-cgv-clic-signature-manuscrite)
- [Prouver le consentement : traçabilité RGPD — Deshoulières Avocats](https://www.deshoulieres-avocats.com/prouver-le-consentement-comment-batir-une-tracabilite-rgpd/)
- [Lignes directrices sur le consentement (WP259) — CNIL](https://www.cnil.fr/sites/cnil/files/atoms/files/ldconsentement_wp259_rev_0.1_fr.pdf)
- [Données personnelles — Enedis](https://www.enedis.fr/donnees-personnelles)
- [J'accède à mes données de mesure (index / quotidien / courbe de charge) — Enedis](https://www.enedis.fr/jaccede-mes-donnees-de-mesure)
- [Compteurs Linky : EDF et Engie mis en demeure par la CNIL — Vie-publique](https://www.vie-publique.fr/en-bref/273429-compteurs-linky-edf-et-engie-mis-en-demeure-par-la-cnil)
- [Sanction de 600 000 € à l'encontre d'EDF (prospection, sécurité — *pas* la courbe de charge) — CNIL](https://www.cnil.fr/fr/prospection-commerciale-et-droits-des-personnes-sanction-de-600-000-euros-lencontre-dedf)
- [Protection des données personnelles et énergie — Seban Avocats](https://www.seban-associes.avocat.fr/protection-des-donnees-personnelles-et-energie/)
