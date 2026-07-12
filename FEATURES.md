# Story map — souscriptions_odoo

Journeys de capacités (`REQ-XXX-nn`), chacune avec un statut (✅ Proven · ⚠️ Contested · 🕳️ Hole) et un pointeur de preuve. Maintenu par le skill `story-map`.

## Parcours : demande de raccordement → mise en service

- REQ-RAC-01 ✅ demande kanban : routage particulier/pro à la création — preuve: tests/test_raccordement_kanban_faits.py::test_routage_creation_particulier_vers_nouveau · #100
- REQ-RAC-02 ✅ validation IBAN (base_iban) et SIRET à la saisie — preuve: tests/test_raccordement.py::test_iban_validation_checksum_invalide · #216
- REQ-RAC-03 ✅ garde d'identité : partner existant réutilisé sans écrasement — preuve: tests/test_raccordement.py::test_existing_partner_reused_without_identity_overwrite · #75
- REQ-RAC-04 ✅ naissance de la souscription à l'acceptation (garde IBAN, coeff pro), portée par `souscription.souscription.naitre_depuis_demande` — la demande n'orchestre plus qu'un intake mince, plus de try/except nu — preuve: tests/test_raccordement_kanban_faits.py::test_naissance_a_laccepte_iban_verifie, tests/test_souscription.py::TestNaissanceDepuisDemande, tests/test_raccordement_kanban_faits.py::test_echec_a_la_naissance_propage_lerreur_dorigine_et_ne_deplace_pas_la_carte · #101, #218
- REQ-RAC-05 ✅ étapes pilotées par les faits : auto-move id_affaire/RSC, drag-in interdit — preuve: tests/test_raccordement_kanban_faits.py::test_auto_move_vers_f120_mes · #90
- REQ-RAC-06 ✅ mails de rassurage à l'entrée des branches F120/F130 — preuve: tests/test_mails_raccordement.py::test_entree_f120_envoie_mail_rassurage · #102
- REQ-RAC-07 ✅ pack de bienvenue automatique à « Abonnement Validé » — preuve: tests/test_mails_raccordement.py::test_drag_en_abonnement_valide_envoie_pack_bienvenue_avec_cp_en_piece_jointe · #103
- REQ-RAC-08 ✅ poll quotidien des affaires Enedis, alertes sans spam — preuve: tests/test_poll_affaires_enedis.py · #89
- REQ-RAC-09 ✅ résolution RSC à la demande via electricore — preuve: tests/test_rsc_service.py · #88
- REQ-RAC-10 ✅ état du contrat calculé : en instance / en service / résiliée — preuve: tests/test_souscription_etat.py::test_bascule_en_service_a_lecriture_de_la_rsc · #87
- REQ-RAC-11 ✅ mandat SEPA créé actif d'emblée via le service `souscription.sepa.mandat` (garde registre `sdd.mandate`, no-op Community) — preuve: tests/test_sepa_mandat.py, tests/test_raccordement.py::test_creer_mandat_sepa_delegue_au_service_et_recopie_le_rum · #187, #217

## Parcours : contrat & documents

- REQ-SOU-01 ✅ souscription base ou HP/HC avec provisions par cadran — preuve: tests/test_souscription.py::test_souscription_creation
- REQ-SOU-02 ✅ tarif solidaire et majoration pro — preuve: tests/test_souscription.py::test_tarif_solidaire
- REQ-SOU-03 ✅ identité Enedis : RSC unique, id_affaire, recherche — preuve: tests/test_souscription_etat.py::test_rsc_dupliquee_refusee · #15
- REQ-SOU-04 ✅ estimation automatique des provisions (electricore) — preuve: tests/test_estimation_provisions.py · #121
- REQ-SOU-05 ✅ journal de consentement append-only — preuve: tests/test_documents_contractuels.py::test_journal_est_append_only_en_ecriture
- REQ-SOU-06 ✅ conditions particulières et attestation PDF — preuve: tests/test_documents_contractuels.py
- REQ-SOU-07 ✅ droits resserrés user/manager sur souscriptions et grilles — preuve: tests/test_security.py · #17

## Parcours : grilles de prix & catalogue

- REQ-GRI-01 ✅ grille active sélectionnée par date, chevauchement interdit — preuve: tests/test_grille_prix.py::test_get_grille_active_par_date · #16
- REQ-GRI-02 ✅ abonnement affine : base 3 kVA + coefficient par kVA — preuve: tests/test_grille_prix.py::test_abonnement_affine_lineaire_dans_la_puissance · #66
- REQ-GRI-03 ✅ régime de prix standard | Moulin par souscription — preuve: tests/test_grille_prix.py::test_get_grille_active_par_regime · #105
- REQ-GRI-04 ✅ duplication en brouillon inactif sans périmer la grille en cours — preuve: tests/test_grille_prix.py::test_dupliquer_grille_ne_perime_pas_la_sœur
- REQ-GRI-05 ✅ catalogue de produits résolu par univers (standard/solidaire) — preuve: tests/test_catalogue.py

## Parcours : cycle mensuel de facturation

- REQ-FAC-01 ✅ campagne mensuelle : DAG d'étapes + portes de vérification — preuve: tests/test_campagne_facturation.py · #156
- REQ-FAC-02 ✅ signaux : statut par souscription, reste-à-faire, drill-down — preuve: tests/test_campagne_signaux.py · #157
- REQ-FAC-03 ✅ boutons d'étape : pulls, créer puis émettre les factures — preuve: tests/test_campagne_etapes_actions.py · #158
- REQ-FAC-04 ✅ notes de campagne reportées au mois suivant — preuve: tests/test_campagne_notes.py · #159
- REQ-FAC-05 ✅ pull des méta-périodes electricore, idempotent — propriétaire durable extrait en service (`souscription.pull.meta.periodes.service`), wizard/Campagne en coquilles minces — preuve: tests/test_pull_meta_periodes.py · #77, #233
- REQ-FAC-06 ✅ énergie par cadran en cascade selon le calendrier de comptage — preuve: tests/test_periode_energie.py · #26
- REQ-FAC-07 ✅ période mensuelle unique, snapshot figé à la facturation — preuve: tests/test_periode_snapshot.py::test_periode_figee_des_la_facturation · #14
- REQ-FAC-08 ✅ relevés d'index : verrou de facturation + bloc justificatif (colonnes = union des familles réellement relevées) — preuve: tests/test_releve.py · #54, #138
- REQ-FAC-09 ✅ composition des lignes : prorata, cadrans, TURPE, pro, solidaire, régime — preuve: tests/test_periode_composition.py · #74
- REQ-FAC-10 ✅ facture d'énergie PDF sur template dédié — preuve: tests/test_invoice_template.py, tests/test_facture_document.py::test_facture_energie_pdf
- REQ-FAC-11 ✅ prestations F15 synchronisées (filtrées par RSC de nos souscriptions, chunké) puis refacturées (TVA par nature) — preuve: tests/test_sync_prestations.py, tests/test_refacturation.py · #147, #245
- REQ-FAC-12 ✅ chèques énergie : imputation FIFO à la facturation — preuve: tests/test_periode_facture.py::test_fifo_par_expiration_le_plus_proche_consomme_en_premier, tests/test_cheque_energie.py · #172
- REQ-FAC-13 ✅ Énergie facturée universelle : la provision, tamponnée `provision := energie` à la facturation pour un contrat non lissé (dé-figeage/refacturation re-tamponne), porte uniformément la quantité facturée ; backfill des non-lissées déjà facturées — preuve: tests/test_periode_composition.py::test_creer_facture_tamponne_la_provision_non_lissee, tests/test_migration_energie_facturee.py · #234
- REQ-FAC-14 ✅ Pull unifié gardé par l'empreinte : `source_hash` inchangé n'écrit rien, empreinte nouvelle + verdict fiable rafraîchit le mesuré v3 en bloc (relevés remplacés en bloc seulement si non facturée), incalculable/mois absent conservé et signalé ; exemption chirurgicale du verrou de facturation sur le mesuré (jamais la provision) ; scope refresh (plage de mois, ne crée rien) pour la Régularisation — preuve: tests/test_pull_meta_periodes.py::TestPullMetaPeriodesService, tests/test_pull_meta_periodes.py::TestPullMetaPeriodesServiceRefresh, tests/test_periode_atterrissage.py::test_champs_atterrissage_reecrivables_apres_facturation · #235

## Parcours : espace usager (portail)

- REQ-POR-01 ✅ accès sécurisé : login, token d'aperçu, cloisonnement entre usagers — preuve: tests/test_portal.py::test_securite_autre_usager
- REQ-POR-02 ✅ historique de consommation inline (factures émises seulement) — preuve: tests/test_portal.py::test_detail_affiche_historique_inline_sans_bouton · #24
- REQ-POR-03 ✅ bloc justificatif des relevés, brouillons non fuités — preuve: tests/test_portal.py::test_releves_periode_emise_visibles · #57

## Parcours : reprise de l'existant

- REQ-MIG-01 ✅ périodes d'ouverture backfillées liées aux factures legacy — preuve: tests/test_periode_ouverture.py · #107
- REQ-MIG-02 ✅ champs d'atterrissage : adresse du PDL, blaze partenaire — preuve: tests/test_souscription.py::test_adresse_pdl_creation, tests/test_res_partner.py::test_blaze_creation · #106
