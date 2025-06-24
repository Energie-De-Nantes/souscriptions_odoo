#!/bin/bash

echo "🔧 Création des données de démo via Odoo shell..."

odoo shell -d souscriptions_demo --addons-path=/home/virgile/addons_odoo << 'EOF'

print("=== Création des données de démo ===")

# Clients de démo
clients_data = [
    {
        "name": "Marie Dupont",
        "is_company": False,
        "street": "15 rue des Énergies Vertes",
        "city": "Rennes",
        "zip": "35000",
        "country_id": env.ref("base.fr").id,
        "email": "marie.dupont@email.fr",
        "phone": "02.99.12.34.56",
    },
    {
        "name": "Jean Martin", 
        "is_company": False,
        "street": "8 avenue du Développement Durable",
        "city": "Nantes",
        "zip": "44000",
        "country_id": env.ref("base.fr").id,
        "email": "jean.martin@email.fr",
        "phone": "02.40.78.90.12",
    },
    {
        "name": "Boulangerie Bio du Coin",
        "is_company": True,
        "street": "3 place du Marché", 
        "city": "Saint-Malo",
        "zip": "35400",
        "country_id": env.ref("base.fr").id,
        "email": "contact@boulangerie-bio.fr",
        "phone": "02.99.56.78.90",
    },
    {
        "name": "Sophie Leroy",
        "is_company": False,
        "street": "12 rue de la Solidarité",
        "city": "Lorient", 
        "zip": "56100",
        "country_id": env.ref("base.fr").id,
        "email": "sophie.leroy@email.fr",
        "phone": "02.97.12.34.56",
    }
]

# Supprimer les clients existants
existing = env["res.partner"].search([("name", "in", [c["name"] for c in clients_data])])
if existing:
    existing.unlink()
    print(f"Supprimé {len(existing)} clients existants")
    
# Créer les clients
clients = env["res.partner"].create(clients_data)
print(f"✅ {len(clients)} clients créés")

# Récupérer l'état de facturation
etat = env["souscription.etat"].search([], limit=1)
if not etat:
    etat = env["souscription.etat"].create({"name": "Actif", "sequence": 1})
    print("État de facturation créé")

# Souscriptions de démo
souscriptions_data = [
    {
        "partner_id": clients[0].id,
        "pdl": "PDL22516914012345", 
        "puissance_souscrite": "6",
        "type_tarif": "base",
        "etat_facturation_id": etat.id,
        "date_debut": "2024-01-01",
        "tarif_solidaire": False,
        "lisse": True,
        "provision_mensuelle_kwh": 280.0,
        "ref_compteur": "85234567",
    },
    {
        "partner_id": clients[1].id,
        "pdl": "PDL22516914098765",
        "puissance_souscrite": "9", 
        "type_tarif": "hphc",
        "etat_facturation_id": etat.id,
        "date_debut": "2024-01-01",
        "tarif_solidaire": False,
        "lisse": True,
        "provision_mensuelle_kwh": 350.0,
        "ref_compteur": "85987654",
    },
    {
        "partner_id": clients[2].id,
        "pdl": "PDL22516914055555",
        "puissance_souscrite": "12",
        "type_tarif": "base", 
        "etat_facturation_id": etat.id,
        "date_debut": "2024-01-01",
        "tarif_solidaire": False,
        "lisse": False,
        "coeff_pro": 15.0,
        "ref_compteur": "85123456",
    },
    {
        "partner_id": clients[3].id,
        "pdl": "PDL22516914033333",
        "puissance_souscrite": "3",
        "type_tarif": "base",
        "etat_facturation_id": etat.id, 
        "date_debut": "2024-01-01",
        "tarif_solidaire": True,
        "lisse": False,
        "ref_compteur": "85456789",
    }
]

# Supprimer les souscriptions existantes
existing_sous = env["souscription.souscription"].search([("pdl", "in", [s["pdl"] for s in souscriptions_data])])
if existing_sous:
    existing_sous.unlink()
    print(f"Supprimé {len(existing_sous)} souscriptions existantes")

# Créer les souscriptions
souscriptions = env["souscription.souscription"].create(souscriptions_data)
print(f"✅ {len(souscriptions)} souscriptions créées")

# Valider les changements
env.cr.commit()
print("🎉 Données de démo créées avec succès !")

print("\n=== Vérification ===")
total_clients = env["res.partner"].search_count([("name", "in", [c["name"] for c in clients_data])])
total_souscriptions = env["souscription.souscription"].search_count([("pdl", "in", [s["pdl"] for s in souscriptions_data])])
print(f"Clients dans la base: {total_clients}")
print(f"Souscriptions dans la base: {total_souscriptions}")

EOF

echo "✅ Script terminé !"