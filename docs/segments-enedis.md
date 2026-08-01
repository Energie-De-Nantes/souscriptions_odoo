# Segments Enedis : particularités de facturation par segment

> Recherche documentaire menée le 26/07/2026 (issue #387, discovery #386).
> Trois volets : réglementaire BT (segments + C4), inventaire HTA, couverture electricore
> (dépôt local, fraîcheur 2026-07-08). Toute affirmation réglementaire cite sa source datée ;
> ce qui n'a pas pu être vérifié sur pièce est dans « Points non confirmés ».
> Le TURPE bouge (prochaine évolution : **+3,04 % au 1er août 2026**, délib. CRE 2026-105) —
> ce document est datable, pas éternel.

## 1. La segmentation C1–C5 — définitions officielles

Source : guide Enedis « Implémentation des flux R6X via compte client entreprise », v2.0 du
29/11/2023, §1.2 « Définition des segments consommateurs / producteurs »
(<https://www.enedis.fr/media/3751/download>). « Segment » est le terme exact d'Enedis.

| Segment | Définition Enedis (verbatim condensé) | Statut |
|---|---|---|
| **C5** | BT ≤ 36 kVA, contrat unique | Notre parc actuel |
| **C4** | BT > 36 kVA, contrat unique | Prochain segment |
| **C3** | HTA, contrat unique, courbe de charge **profilée** | **Obsolète depuis 01/2023** |
| **C2** | HTA, contrat unique, courbe de charge **mesurée** | Le segment HTA vivant |
| **C1** | Tout point auquel est associé un **contrat CARD** | Défini par le contrat, pas la tension |

Points structurants :

- **La liste vivante côté fourniture est C5, C4, C2.** C3 a disparu (plus de profilage en
  HTA : tout site HTA en contrat unique est C2). C1 = CARD : le client paie le TURPE et la
  CTA **directement à Enedis** — le fournisseur d'un C1 ne facture que l'énergie (brochure
  TURPE 7, p. 19–20). Un C1 ne mobiliserait donc presque rien de notre chaîne acheminement.
- **Il existe aussi des segments producteurs P1–P4** (même guide) — hors périmètre fourniture.
- Domaines de tension (brochure TURPE 7, p. 20) : BT = U ≤ 1 kV ; HTA = 1 kV < U ≤ 50 kV.
- **Qui définit quoi** : la segmentation C1–C5 est une segmentation **Enedis / SI marché**
  (C5+P4 dans le SI ≤ 36 kVA, C4+C2+P3 dans le SI > 36 kVA — note Enedis-MOP-CF_081E du
  15/09/2025, <https://www.enedis.fr/media/2910/download>). **La CRE ne raisonne jamais en
  segments** mais en domaines de tension (HTA, BT > 36, BT ≤ 36).
- **Méfiance envers les vulgarisations** : les blogs de courtiers (« C1 = > 250 kVA très
  haute tension », « C4 = 37–250 kVA ») ne correspondent pas aux définitions Enedis. La borne
  250 kVA est vraisemblablement la limite de raccordement BT (à confirmer).
- **Le segment arrive dans les flux** : le C15 porte `Segment_Clientele` nativement (ingéré
  par electricore, jamais lu) ; le C12 ne le porte pas — il s'infère du domaine de tension et
  de la FTA (electricore ADR-0051).

## 2. C5 — le cas connu (rappel de référence)

TURPE 7 : délibération CRE n° 2025-78 du 13/03/2025, JO du 14/05/2025, grilles en vigueur au
**1er août 2025** (brochure Enedis <https://www.enedis.fr/media/4717/download>, p. 3, 16–18).

- **CG** 16,80 €/an (contrat unique) ; **CC** 22,00 €/an ; **CACNC** (compteur non
  communicant, propre au C5) 6,48 €/bimestre + majoration.
- **CS** : une **seule puissance** souscrite (kVA), `CS = b × P + Σ cᵢ·Eᵢ`, 5 FTA
  (CU4, MU4, LU + dérogatoires CU/MUDT), 4 classes temporelles max (HPH/HCH/HPB/HCB).
- **Pas de CMDPS** : les dépassements sont « sans objet » quand la puissance est contrôlée
  par disjoncteur ou compteur évolué (brochure p. 7) — c'est le cas du C5.
- Flux : C15 (contractuel), R15/R151 (index, Pmax quotidienne), R50 (CdC), F15 (acheminement).

## 3. C4 (BT > 36 kVA) — ce qui change

Source principale : brochure TURPE 7 pp. 13–15 (valeurs HT au 01/08/2025).

### 3.1 Structure tarifaire

- **4 puissances souscrites**, une par classe temporelle (HPH, HCH, HPB, HCB), en **kVA**,
  par multiples de 1 kVA, **croissantes** (Pᵢ₊₁ ≥ Pᵢ). **Pas de classe Pointe** (HTA
  seulement). 2 options : CU, LU.
- **CS en cascade** : `CS = b₁·P₁ + Σᵢ₌₂⁴ bᵢ·(Pᵢ−Pᵢ₋₁) + Σᵢ cᵢ·Eᵢ`.
  b(CU) = 17,61/15,96/14,56/11,98 €/kVA/an ; c(CU) = 6,91/4,21/2,13/1,52 c€/kWh (au
  01/08/2025 ; +3,04 % au 01/08/2026, délib. CRE 2026-105 du 21/05/2026).
- **CMDPS (dépassements)** : par plage temporelle et par mois, **`CMDPS = 12,41 €/h × h`**
  (h = durée de dépassement de la puissance apparente souscrite, en heures). **Formule
  horaire simple — la quadratique au pas 10 min est HTA, pas C4.** 12,79 €/h au 01/08/2026.
  Plafonnement possible **sur demande au GRD** (30 % de la facture TURPE mensuelle / 25× le
  tarif de la puissance manquante, brochure p. 15). Contrôle sur puissance active =
  puissance apparente × 0,93 (p. 6).
- **CG ≈ 13× le C5** : 217,80 €/an ; **CC** 283,27 €/an, transmission **mensuelle** minimum.
  Pas de CACNC. **Pas de CER** : depuis TURPE 7, l'énergie réactive n'est plus facturée en
  BT > 36 (brochure p. 15) — c'est un point qui a changé avec TURPE 7.
- **Fourniture libre** : plus de TRV au-dessus de 36 kVA (fin des Tarifs Jaunes). La CG du
  contrat unique inclut la rémunération fournisseur Rf (90,06 €/an BT > 36 au 01/08/2026).

### 3.2 Fiscalité

- **Accise** : le C4 professionnel bascule de catégorie fiscale — **« PME » (36 < P ≤ 250
  kVA)**, pas « ménages et assimilés » (art. L312-24 CIBS ; tarifs 2025 sur impots.gouv.fr :
  ménages 33,70 puis 29,98 €/MWh, PME 26,23 puis 25,79 €/MWh). **C'est le vrai saut fiscal —
  il se joue au franchissement des 36 kVA, pas à l'HTA.** Côté electricore, c'est l'issue
  #226 (catégorie d'accise), matière première (`code_ape`, domaine de tension) déjà ingérée
  via C12 mais aucune règle ne la consomme.
- **CTA** : même mécanisme et même taux distribution que le C5 (21,93 % → **15 % au
  01/02/2026**, arrêté du 28/01/2026) ; seule l'assiette grossit (éléments fixes C4).
- **TVA** : inchangée (assise sur tout, CTA et accise comprises).

### 3.3 Comptage et flux — où vivent les données C4

Compteurs ICE/PME-PMI/SAPHIR (pas de Linky). La partition des flux fournisseur (note
Enedis-MOP-CF_081E) : **pour les PRM > 36 kVA, les homologues de C15/R15·R151/F15 sont
C12/R17/F12.**

| Besoin | Flux C4 | Contenu (sources : guides R17 GÉRÉDIS 01/01/2024, R4x Enedis.SGE.GUI.0408 v2.0.2, F15 « bordereau » GÉRÉDIS 01/08/2025 — kit marché au format Enedis) |
|---|---|---|
| Contractuel | **C12** | FTA, domaine de tension, **4 puissances par classe**, code APE, raison sociale |
| Index / énergies | **R17** | Index actifs **et réactifs** par classe temporelle, conso par classe selon tarification TURPE, ≥ 1×/mois |
| **Dépassements** | **R17** | **Durée de dépassement, dépassement énergétique, dépassement quadratique, puissance max atteinte** — calculés par Enedis, livrés par classe |
| Courbe de charge | **R4Q/R4H/R4M** | CdC active/réactive/tension, pas porté par la balise `Granularite` (10 min usuel marché ; 5 min côté compte client — à confirmer) |
| Acheminement facturé | **F12** | TURPE **poste par poste**, CMDPS incluse ligne à ligne (libellés type « dépassements de puissance HCH », article `ACHCMDPS` chez SRD) |

**La réponse à « où chercher les composantes de dépassement » est donc : le flux R17** —
Enedis calcule et livre les agrégats de dépassement, il n'y a **pas** à les recalculer depuis
la courbe de charge. Et le **F12** porte la CMDPS *facturée* par Enedis, utilisable en
contrôle (ou en refacturation au réel).

### 3.4 Pratique de refacturation

- **CMDPS refacturée à l'identique** : pratique dominante sourcée (FAQ ENGIE Pro : « le
  montant collecté est reversé à Enedis ») — le fournisseur est collecteur transparent.
  Structurellement, c'est le motif de notre **Refacturation (Enedis)** : un en-cours d'origine
  Enedis refacturé au souscripteur — piste naturelle côté module, à étudier au design C4.
- **TURPE en transparence vs absorbé** : aucune obligation, les deux pratiques existent
  (pratique commerciale libre). Notre ADR 0002 (TURPE absorbé dans la grille) reste un choix
  possible en C4 — mais la CMDPS, imprévisible par nature, se prête mal à l'absorption.

## 4. HTA (C2, et C1 en CARD) — inventaire

Source : brochure TURPE 7 pp. 5–12, 19–20 ; délib. CRE 2025-78. Équation générale :
`TURPE = CG + CC + CS + CMDPS + CACS + CR + CER + CI + CT + CACNC` (certaines composantes
nulles selon le mode d'utilisation).

Ce que l'HTA ajoute **par rapport au C4** :

1. **5ᵉ classe temporelle : Pointe**, en deux variantes — **fixe** (2 h matin + 2 h soir,
   déc.–févr.) ou **mobile** (heures PP1 du mécanisme de capacité, **déterminées par RTE la
   veille pour le lendemain**, 10–15 jours/an). 4 FTA : CU/LU × pointe fixe/mobile. Le
   calendrier tarifaire devient dépendant d'un signal externe J-1.
2. **Puissances en kW** (plus kVA), une par classe, croissantes, 5 valeurs.
3. **CMDPS quadratique** : `CMDPS = Σ 0,04 × bᵢ × √(Σ ΔP²)`, ΔP = dépassement **par pas de
   10 minutes**. Le « dépassement quadratique » (DQ) est **publié par Enedis** dans les
   mesures R17/R6X — même logique que le C4 : la donnée arrive calculée.
4. **CER — énergie réactive** : *seuls les clients HTA* la paient sous TURPE 7. Gratuite
   jusqu'à tg φ = 0,40 en pointe/HPH de saison haute (nov.–mars), **2,44 c€/kVAr·h**
   au-delà ; règles spécifiques injection (tg φ 0,60, 2,39/2,96 c€/kVAr·h). Nouvelles
   grandeurs à modéliser : kVAr·h inductif/capacitif par période.
5. **CACS** (alimentations complémentaires/de secours) et **CR** (regroupement) : composantes
   assises sur des **caractéristiques physiques du raccordement** (cellules, km de liaison,
   regroupement conventionnel de points) — attributs statiques du PDL, pas des mesures.
6. **CG/CC HTA** : 435,72 €/an (contrat unique) / 376,39 €/an — transmission mensuelle.
7. **Dispositif contractuel comme dimension** : CARD (C1) vs contrat unique (C2). En CARD,
   TURPE **et** CTA sont facturés au client par Enedis — le fournisseur ne facture que
   l'énergie. À modéliser comme attribut du contrat même si on ne sert que du contrat unique.
8. **Fiscalité : rien de spécifiquement HTA** — la catégorie d'accise a déjà basculé à
   36 kVA ; CTA au même taux distribution. Tarifs réduits d'accise (électro-intensifs) plus
   probables sur ce segment (à confirmer).

## 5. Couverture electricore (état au 2026-07-08)

Rapport détaillé sur le dépôt local (`electricore/core/pipelines/turpe.py`,
`config/turpe_rules.csv`, ADR-0051, `docs/turpe-fixe-c4-btsup36kva.md`).

| Segment | Couvert | Manquant (bloquant en gras) |
|---|---|---|
| **C5** | Complet, en production : TURPE 6+7 fixe/variable, 9 FTA `BTINF*`, CTA, accise (taux ménages), contrat méta-périodes v3, calculateur RPC 7 cadrans, flux C15/R151/R15/R64/R67/F15/F12 | Enum `categorie_produit` fermée à Base/HP/HC (4 cadrans facturés impossibles) |
| **C4** | **Cœur de calcul prêt et testé** : TURPE fixe 4 puissances + détection auto, validateur de monotonie, CMDPS horaire, coefficients TURPE 7 `BTSUPCU`/`BTSUPLU` ; **C12 ingéré** (pivot des 4 puissances, ADR-0051) ; **F12 ingéré** ; registres d'index 7 cadrans déjà exposés dans `releves_utilises` | **(1) FTA réelles `BTSUPCU4`/`BTSUPLU4` absentes de `turpe_rules.csv`** (seules les variantes sans « 4 » y sont) → « FTA inconnue » sur un vrai C4 ; **(2) C12 ne alimente aucun pipeline** (la spine ne lit que C15) ; **(3) flux R17 non ingéré** → aucune durée de dépassement ne peut entrer (la CMDPS attend `duree_depassement_h` de l'appelant) ; (4) les 4 puissances non projetées par le pipeline abonnements ; (5) contrat méta-périodes explicitement « C4 hors périmètre v1 » (extension prévue en colonnes additives) ; (6) calculateur RPC sans composante dépassement (déclaré hors v1) ; (7) catégorie d'accise PME non tranchée (leur #226) ; (8) pas de TURPE 6 C4 (grille démarre au 01/08/2025) |
| **C2 (HTA)** | Quasi rien : C12 « C2-C4 » ingéré, XSD connaît les FTA HTA | Tout : zéro ligne HTA dans la grille, pas de classe Pointe (7 cadrans canoniques sans « pointe »), pas de formule 5 puissances, pas de CMDPS quadratique, pas d'énergie réactive (le filtre R64 la jette), classes HTA du C12 délibérément non mappées (ADR-0051), pas de CACS/CR |
| **C1** | Aucune trace | Intégralité (mais périmètre fournisseur réduit : énergie seule) |

Deux pièges relevés par l'exploration :

- **La détection C4 est purement tarifaire** (présence des coefficients `b_*` dans la règle
  jointe) : ajouter une ligne HTA au CSV ferait basculer silencieusement un PDL HTA sur la
  formule C4 — fausse (5 postes, réactive, comptage différent). Aucun garde-fou.
- **`segment_clientele` (C15) traverse toute la chaîne sans jamais être lu.** Le brancher est
  le chemin le plus court vers une conscience de segment explicite côté electricore — et la
  future source autoritative du champ segment côté Odoo.

## 6. Implications pour le module (esquisse, pas un design)

- **Le squelette tient pour tous les segments** : Souscription + Période + Facture d'énergie,
  règlements/compta parc-entier (CONTEXT.md « Segment (Enedis) »). Rien dans la recherche ne
  l'infirme.
- **C4** : les nouveautés sont *additives* — 4 puissances (vs 1), une composante CMDPS qui
  arrive **déjà calculée** (R17) et **déjà facturée ligne à ligne** (F12). La CMDPS
  refacturée à l'identique épouse le motif **Refacturation (Enedis)** existant. Le plafond
  `puissance_souscrite` (Selection ≤ 36 kVA) et l'abonnement affine ADR 0018 (pensé
  mono-puissance) sont les deux points durs côté module.
- **C2 (HTA)** : classe Pointe (calendrier dépendant d'un signal RTE J-1 en pointe mobile),
  kW, réactive, CACS/CR statiques — un autre monde de mesure. Ne rien pré-modéliser.
- **C1 (CARD)** : quasi hors périmètre acheminement — facture d'énergie seule.

## 7. Recommandation sur la tranche minimale de #386

**Construire la tranche minimale maintenant.** Champ `segment` sur la Souscription (Selection,
défaut `c5`, snapshot à la main — précédent `config_cadrans`) + Périmètre de campagne filtré
C5. Arguments :

1. **La classification est officielle, stable et déjà dans nos flux** (C15
   `Segment_Clientele`) — le champ ne modélise pas une spéculation, il nomme un fait réseau
   que la chaîne transporte déjà.
2. **Le gate campagne ferme un vrai risque** : un C4 entré au parc serait aujourd'hui balayé
   par la création/émission en masse avec une grille incapable de le prixer (abonnement
   affine mono-puissance, pas de CMDPS) — l'échec bruyant au milieu d'une campagne de 800
   factures est le mauvais endroit pour découvrir un segment.
3. **C'est l'ancre de tout l'incrémental** : electricore prévoit l'extension C4 « en colonnes
   additionnelles sans rupture » (contrat méta-périodes) ; côté Odoo, le champ segment est le
   point d'accroche qui routera ces colonnes le jour venu.
4. **Le coût est minimal** : un champ + un terme de domaine dans le périmètre — pas de
   campagne par segment, pas de modèle C4, pas de classe Pointe.

**Ne pas construire maintenant** (confirmé par la recherche) : le déplafonnement de
`puissance_souscrite` et l'abonnement 4 puissances (tranche « premier C4 », déclenchée par la
réalité — et gated côté electricore par leurs trous (1)(2)(3) du §5) ; toute modélisation HTA
(C2 est un autre monde, et C3 n'existe plus) ; la campagne par segment (attendre de connaître
les étapes réelles d'un process C4).

## Points non confirmés

- Borne haute « 250 kVA » du C4 (vulgarisation courtiers ; vraisemblablement la limite de
  raccordement BT — à confirmer doc raccordement Enedis).
- Libellés exacts des articles CMDPS dans le **F12 Enedis** (démontrés sur les
  implémentations ELD au format Enedis ; spec F12 derrière le portail SGE).
- Pas effectif de la courbe de charge C4 dans le **R4Q Enedis** (10 min côté marché vs 5 min
  côté compte client entreprise).
- Tarifs d'accise au 01/02/2026 (FNCCR : ménages 24,69 / entreprises 20,42 €/MWh, fusion des
  catégories PME et haute puissance — non vérifié sur texte consolidé). **À vérifier aussi
  côté electricore : `accise_rules.csv` s'arrête au 01/08/2025 (29,98).**
- Tarifs réduits d'accise (électro-intensifs, arrêté du 18/12/2025) — presse spécialisée
  seulement.
- Part du marché HTA en CARD vs contrat unique (aucune statistique publique trouvée).
- Existence résiduelle de points C3 (« obsolète depuis 01/2023 » ; pas de délibération de
  bascule consultée).
- Guides R17/R15/R151/F15 cités via des GRD ELD au format Enedis (kit marché) — les specs
  Enedis SGE elles-mêmes sont derrière le portail fournisseur ; écarts de détail possibles.

## Sources principales

| Source | Date | URL |
|---|---|---|
| Brochure Enedis TURPE 7 HTA/BT (tarifs au 01/08/2025) | 2025-08 | <https://www.enedis.fr/media/4717/download> |
| Délibération CRE n° 2025-78 (TURPE 7) | 2025-03-13 | <https://www.cre.fr/fileadmin/Documents/Deliberations/2025/250313_2025-78_Post-CSE_TURPE_7_HTA-BT.pdf> |
| Délibération CRE n° 2026-105 (évolution +3,04 % au 01/08/2026) | 2026-05-21 | <https://www.cre.fr/fileadmin/Documents/Deliberations/2026/260521_2026-105_Evolution_TURPE_7_HTA-BT.pdf> |
| Guide Enedis flux R6X (définition des segments, mesures > 36 kVA) | 2023-11-29 | <https://www.enedis.fr/media/3751/download> |
| Note Enedis-MOP-CF_081E (partition des flux C12/R17/F12) | 2025-09-15 | <https://www.enedis.fr/media/2910/download> |
| Guide flux R17 (kit marché, implémentation GÉRÉDIS) | 2024-01-01 | <https://www.geredis.fr/IMG/pdf/guide_d_implementation_flux_r17_geredis.pdf> |
| Guide flux R4x Enedis.SGE.GUI.0408 v2.0.2 (repro. Strasbourg É.R.) | 2019-03-25 | <https://www.strasbourg-electricite-reseaux.fr/file/14820> |
| Arrêté du 28/01/2026 (CTA 15 % / 5 % au 01/02/2026) | 2026-01-28 | <https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000053417026> |
| Art. L312-24 CIBS (catégories fiscales d'accise) | consulté 2026-07-26 | <https://www.legifrance.gouv.fr/codes/section_lc/LEGITEXT000044595989/LEGISCTA000044598377/> |
| Tarifs accise 2025 (impots.gouv.fr) | 2025 | <https://www.impots.gouv.fr/actualite/consommation-denergie-tarifs-normaux-des-accises-en-2025> |
| FAQ ENGIE Pro (pratique CMDPS reversée) | consulté 2026-07-26 | <https://pro.engie.fr/faq/tout-sur-l-energie/composante-mensuelle-des-depassements-de-puissance-souscrite> |
