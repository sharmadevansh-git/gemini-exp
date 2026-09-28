import subprocess
import sys
import google.oauth2.credentials
from google.cloud import firestore

FIRESTORE_PROJECT_ID = "qwiklabs-gcp-02-4c44a765ce09"

def get_credentials():
    try:
        token = subprocess.check_output(["gcloud", "auth", "print-access-token"]).decode("utf-8").strip()
        return google.oauth2.credentials.Credentials(token)
    except Exception as e:
        print(f"Warning: Could not get gcloud access token: {e}")
        return None

def seed_database():
    print(f"Connecting to Firestore for project: {FIRESTORE_PROJECT_ID}...")
    creds = get_credentials()
    db = firestore.Client(project=FIRESTORE_PROJECT_ID, credentials=creds, database="(default)")

    # Spells collection
    spells = [
        {
            "id": "fireball",
            "name": "Fireball",
            "level": 3,
            "school": "Evocation",
            "casting_time": "1 action",
            "range": "150 feet",
            "damage": "8d6 Fire",
            "description": "A bright streak flashes from your finger to a point you choose within range and then blossoms with a low roar into an explosion of flame."
        },
        {
            "id": "cure_wounds",
            "name": "Cure Wounds",
            "level": 1,
            "school": "Evocation",
            "casting_time": "1 action",
            "range": "Touch",
            "damage": "1d8 + modifier Healing",
            "description": "A creature you touch regains a number of hit points equal to 1d8 + your spellcasting ability modifier."
        },
        {
            "id": "magic_missile",
            "name": "Magic Missile",
            "level": 1,
            "school": "Evocation",
            "casting_time": "1 action",
            "range": "120 feet",
            "damage": "3d4 + 3 Force",
            "description": "You create three glowing darts of magical force. Each dart automatically hits a target of your choice."
        },
        {
            "id": "shield",
            "name": "Shield",
            "level": 1,
            "school": "Abjuration",
            "casting_time": "1 reaction",
            "range": "Self",
            "damage": "None (+5 AC)",
            "description": "An invisible barrier of magical force appears and protects you, adding +5 to AC until the start of your next turn."
        },
        {
            "id": "lightning_bolt",
            "name": "Lightning Bolt",
            "level": 3,
            "school": "Evocation",
            "casting_time": "1 action",
            "range": "Self (100-foot line)",
            "damage": "8d6 Lightning",
            "description": "A stroke of lightning forming a line 100 feet long and 5 feet wide blasts out from you."
        }
    ]

    for spell in spells:
        doc_ref = db.collection("spells").document(spell["id"])
        doc_ref.set(spell)
        print(f"Seeded spell: {spell['name']}")

    # Inventory collection
    inventory_items = [
        {
            "id": "potion_of_healing",
            "item_name": "Potion of Healing",
            "item_type": "Consumable",
            "quantity": 5,
            "description": "A magical red liquid that restores 2d4+2 hit points."
        },
        {
            "id": "bag_of_holding",
            "item_name": "Bag of Holding",
            "item_type": "Wondrous Item",
            "quantity": 1,
            "description": "Holds up to 500 pounds without getting heavier."
        },
        {
            "id": "longsword_plus_1",
            "item_name": "+1 Longsword",
            "item_type": "Weapon",
            "quantity": 1,
            "description": "A magical sword granting +1 bonus to attack and damage rolls."
        }
    ]

    for item in inventory_items:
        doc_ref = db.collection("inventory").document(item["id"])
        doc_ref.set(item)
        print(f"Seeded inventory item: {item['item_name']}")

    print("Firestore database seeding completed successfully!")

if __name__ == "__main__":
    seed_database()
