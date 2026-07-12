# La fin de souscription gouvernée par le fait C15 : sorties tirées, date de fin à auteur unique, clôture à la campagne

Instruit le chantier résiliations et déménagements (#21, concrétise #7) — instruit en session le
2026-07-12, dans la foulée du chantier régularisation (ADR-0030, PRD #231) dont il réutilise la
mécanique. Point de départ : la fin de vie est aujourd'hui **passive** — `etat` dérive de
`date_fin < today`, mais `date_fin` est un champ nu que rien n'écrit (ni action, ni cron, ni
ingestion). La source de vérité est le **C15**, codes de sortie `{RES, CFNS}` — résiliation et
changement de fournisseur sortant, **symétriques** pour nous. Côté electricore, l'ADR-0052 (adossé
à un spike sur 2 204 événements C15 réels) a établi les faits porteurs : une RSC ne se rouvre
jamais, une sortie au plus par RSC, les codes portent la date (le flag `etat_contractuel` n'est
qu'un garde-fou). Mais rien de tout cela n'est exposé en contrat consommable : le contrat v3 des
méta-périodes ne porte aucune information de fin, et les sorties ne sortent qu'en XLSX pour
humains. Conventions vérifiées dans le code : la Période est demi-ouverte
(`jours = date_fin − date_debut`, bornes v3 brutes), la souscription est lue en **inclusif** aux
deux endroits qui comptent (`_compute_etat`, périmètre de campagne).

**Décisions.**

1. **Le canal : les sorties C15 tirées, filtrées par RSC à la requête.** Nouvel endpoint
   electricore typé (contrat v1 enveloppé, style `resoudre_rsc`) des sorties C15
   `{RES, CFNS}` : payload minimal `{rsc, pdl, evenement, date}` — les index sont déjà dans les
   relevés, on ne vient chercher qu'un type et une date. Le filtre RSC est **à la requête** et la
   liste vient d'Odoo : les périmètres Enedis peuvent être partagés entre entités, indistinguables
   dans les flux — l'autorité du « à nous » est la souscription. Méthode client + release + bump
   du pin (`electricore-client==0.4.0` →). Propriété clé, **auto-cicatrisant** : chaque passage
   interroge toutes les souscriptions non résiliées ; une sortie ratée un mois ou un C15 en retard
   ressortent au passage suivant. Clé d'idempotence : la **RSC seule** (unicité prouvée au spike
   ADR-0052). Volume : quelques dizaines de sorties par mois, re-pull sans état ni fenêtre.

2. **Application directe — pas de modèle-file.** Le pull écrit `date_fin` sur la souscription,
   sans table intermédiaire : la sortie porte deux scalaires qui se projettent intégralement
   (date → `date_fin`, provenance → chatter). Idempotence par comparaison de champ : absente →
   écrire + message chatter (code, date brute) ; identique → noop ; différente → corriger +
   trace. `date_fin` devient **readonly, à auteur unique** — le fait C15, comme la naissance a un
   seul auteur (#226). Jamais de saisie manuelle : l'anticipation n'est pas modélisée, les ratés
   (résiliation exécutée plus tard que demandée…) relèvent du geste commercial (#35). Convention
   de borne : le C15 est demi-ouvert (« résilié le J ⟹ absent dès J », ADR-0052/0042) →
   **`date_fin = J − 1`, dernier jour servi**. Ce choix préserve la lecture inclusive déjà codée —
   l'état bascule dès J, le périmètre de campagne inclut le mois de sortie et exclut le suivant
   même quand J tombe un 1ᵉʳ — et le sens des `date_fin` migrées (ADR-0023). La Période, elle,
   reste demi-ouverte ; la conversion vit à la couture du pull, documentée au glossaire.

3. **Un quatrième état dérivé : « en attente de clôture ».** `en_service` →
   `en_attente_cloture` (date de fin passée ∧ clôture non soldée) → `resiliee` (clôture soldée).
   Prédicat de faits, aucun statut à la main : **clôture soldée ⟺ la Période contenant
   `date_fin` est facturée ∧ (une Régularisation de clôture est émise ∨ rien à solder)**. Le
   « rien à solder » fait passer directement en `resiliee` les non-lissés (écarts nuls par
   construction) et les résiliés migrés (mois à l'état « régularisée », ADR-0023/PRD #207). **La
   file d'attente de traitement des sorties, c'est la vue de cet état** — le fait se transforme
   en travail sans objet supplémentaire.

4. **La clôture se facture à la campagne, deux documents.** C'est nous qui tenons le calendrier
   de facturation : aucune course contre l'information, pas de branche « su avant / su après ».
   Ordre dans la campagne : pull des sorties → `date_fin` → périmètre → pull des méta-périodes →
   mensuelles → réguls de clôture. La dernière mensuelle se facture **au réel** — la branche
   tampon `provision := energie` de l'ADR-0030 (décision 2) appliquée à la dernière période d'un
   lissé : jours exacts et énergie exacte viennent d'electricore, la facture porte ses
   relevés-justificatifs comme n'importe quelle mensuelle. Si la mensualité pleine est déjà
   partie, l'écart du dernier mois ravive le tampon et la régul l'avale — aucun cas spécial. La
   **régul de clôture est une Régularisation ordinaire** (candidats ADR-0030 : mois facturés à
   écart non nul, mesuré connu, non soldés) ; net négatif → avoir. À son émission, **tous les
   mois de la souscription passent à l'état « régularisée »** — le marqueur d'exclusion
   définitive gagne un second auteur (migration, clôture) : le livre est fermé, aucun candidat ne
   renaît même si electricore raffine encore le mesuré.

5. **Hors mécanisme, cas humains nommés.** La demande de résiliation **sortante** (le client nous
   appelle, nous déposons la demande auprès d'Enedis) est un process à côté, différé — candidat à
   un suivi type affaires ; sa sortie retombe dans le même entonnoir C15. Une **annulation ou un
   redatage** d'une sortie après clôture n'est pas détecté automatiquement (le re-pull ne montre
   qu'une absence) : traitement humain, assumé. v1 dans le sillage du chantier régularisation :
   compteurs communicants.

## Options écartées

- **Flag `fin_contrat` sur la méta-période** : information de contrat déguisée en information de
  période — élargit le contrat v3 pour tous les consommateurs, à jamais, pour une donnée utile
  une fois.
- **Endpoint spans (primitive ADR-0052 par RSC)** : un état, pas un travail — il faut le differ
  contre les souscriptions à chaque passage ; l'événement de sortie est déjà l'unité de travail.
  La primitive reste disponible pour le reporting.
- **« Sorties du mois » fenêtré** : rate les C15 rétroactifs et les passages sautés ; l'interroger
  par plages réinvente mal le filtre par RSC.
- **Inférence Odoo via `releves_utilises[].evenement`** : métier C15 réinterprété côté ERP,
  contrat implicite — contre la division des responsabilités electricore/Odoo.
- **Modèle-file des sorties (motif F15 complet)** : la prestation F15 porte du contenu facturable
  (montants, taxes, futures lignes) ; la sortie, deux scalaires. Et un statut de traitement posé à
  la main est précisément ce que les états dérivés refusent partout ailleurs.
- **`date_fin` saisissable (anticipation)** : un deuxième auteur pour un champ gouverné par le
  fait ; l'anticipation vit dans le process à côté (décision 5).
- **`/flux/c15/sorties.xlsx`** : export pour humains — sans contrat JSON, sans typage client, sans
  garde de version.
- **Facture unique « régul-résiliation »** : obligerait la Régularisation à facturer une Période
  entière jamais facturée — règle des candidats tordue, un objet à deux métiers.

## Conséquences

- **Issue electricore** à ouvrir : endpoint sorties C15 typé + méthode client + release ; bump du
  pin côté addon. **Micro-issue F15** au passage : passer `rsc=` à la requête (`prestations()`
  tire aujourd'hui tout le périmètre ; la résolution à l'insertion couvre déjà la sémantique —
  hygiène de fil seulement).
- **Branchement** : le propriétaire durable du pull (PRD #231, tranches #233/#235) est le point
  d'accroche du pull des sorties — le chantier suit ces tranches.
- `_compute_etat` gagne une valeur dérivée (`en_attente_cloture`) et une dépendance au prédicat de
  clôture. La limite « compute stocké vs passage du temps » devient théorique : le C15 arrive
  toujours après l'effet, l'écriture déclenche le recompute — documentée, pas de cron dédié.
- Le périmètre de campagne est **inchangé** (il lit déjà `date_fin`).
- Portail : refléter le statut. Suivis nommés et différés : facture prestations-seules
  post-résiliation (ADR-0009), mails automatiques (#92), suivi de la demande de résiliation
  sortante (décision 5).
- CONTEXT.md : l'entrée cycle de vie (« la résiliation est un chantier distinct ») est remplacée
  par les quatre états ; glossaire : convention de borne (souscription inclusive « dernier jour
  servi » / Période demi-ouverte).
- Tests : cycle complet `en_service` → `en_attente_cloture` → `resiliee` ; les critères
  d'acceptation de #21 (dernière facture aux jours exacts, plus aucune période ni facture après,
  statut reflété) sont couverts par ce modèle.
