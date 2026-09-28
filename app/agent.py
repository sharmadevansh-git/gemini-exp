# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.adk.agents.callback_context import CallbackContext
from google.adk.memory import VertexAiMemoryBankService
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.genai import types
from google.cloud import firestore, storage
from google import genai
import base64

from app.a2ui_instruction import INSTRUCTION as instruction
from app.a2ui_utils import a2ui_callback

MODEL = "gemini-2.5-flash"
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-02-4c44a765ce09"
BUCKET_NAME = "rpg-party-assets-4c44a765ce09"
AGENT_ENGINE_RESOURCE_NAME = "projects/635220904438/locations/us-east1/reasoningEngines/3872380996980572160"
SANDBOX_RESOURCE_NAME = "projects/635220904438/locations/us-east1/reasoningEngines/3872380996980572160/sandboxEnvironments/5325093142993567744"
MEMORY_BANK_ID = "3872380996980572160"


# Memory generation callback for durable cross-session facts/preferences
async def generate_memories_callback(callback_context: CallbackContext):
    await callback_context.add_session_to_memory()
    return None

# Memory service builder for deployment
def memory_bank_service_builder():
    return VertexAiMemoryBankService(
        project=FIRESTORE_PROJECT_ID,
        location="us-east1",
        agent_engine_id=MEMORY_BANK_ID,
    )

import threading

class PicklableAgentEngineSandboxCodeExecutor(AgentEngineSandboxCodeExecutor):
    def __getstate__(self):
        state = dict(self.__dict__)
        state["_agent_engine_creation_lock"] = None
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        if getattr(self, "_agent_engine_creation_lock", None) is None:
            self._agent_engine_creation_lock = threading.Lock()

# Initialize AgentEngine Sandbox Code Executor
code_executor = PicklableAgentEngineSandboxCodeExecutor(
    sandbox_resource_name=SANDBOX_RESOURCE_NAME,
    agent_engine_resource_name=AGENT_ENGINE_RESOURCE_NAME,
)


def get_db():
    return firestore.Client(project=FIRESTORE_PROJECT_ID)


def get_spells(level: int = None, school: str = None) -> str:
    """Retrieves spells from the party spellbook.

    Args:
        level: Optional spell level integer (e.g. 1, 3) to filter by.
        school: Optional magic school string (e.g. Evocation, Abjuration) to filter by.

    Returns:
        A formatted string listing all matching spells in the spellbook.
    """
    try:
        db = get_db()
        spells_ref = db.collection("spells")
        docs = spells_ref.stream()

        results = []
        for doc in docs:
            data = doc.to_dict()
            if level is not None and data.get("level") != level:
                continue
            if school and data.get("school", "").lower() != school.lower():
                continue
            results.append(
                f"- **{data.get('name')}** (Level {data.get('level')} {data.get('school')}): "
                f"Range: {data.get('range')}, Damage/Effect: {data.get('damage')}. "
                f"Description: {data.get('description')}"
            )

        if not results:
            return "No matching spells found in the spellbook."
        return "### Known Spells:\n" + "\n".join(results)
    except Exception as e:
        return f"Error retrieving spells from Firestore: {e}"


def add_spell(name: str, level: int, school: str, casting_time: str, range_dist: str, damage: str, description: str) -> str:
    """Adds a new spell to the party spellbook in Firestore.

    Args:
        name: Name of the spell (e.g. "Fireball").
        level: Spell level integer (0-9).
        school: Magic school (e.g. "Evocation", "Abjuration").
        casting_time: Time needed to cast (e.g. "1 action", "1 bonus action").
        range_dist: Casting range or area (e.g. "150 feet", "Touch").
        damage: Damage or healing formula (e.g. "8d6 Fire", "2d8 Healing").
        description: Detailed effect description.

    Returns:
        A confirmation message upon successfully storing the spell.
    """
    try:
        db = get_db()
        spell_id = name.lower().replace(" ", "_")
        doc_ref = db.collection("spells").document(spell_id)
        spell_data = {
            "id": spell_id,
            "name": name,
            "level": level,
            "school": school,
            "casting_time": casting_time,
            "range": range_dist,
            "damage": damage,
            "description": description,
        }
        doc_ref.set(spell_data)
        return f"Successfully added spell '{name}' (Level {level} {school}) to the spellbook."
    except Exception as e:
        return f"Error adding spell to Firestore: {e}"


def get_inventory() -> str:
    """Retrieves all items currently stored in the party inventory.

    Returns:
        A formatted string listing all items, quantities, and descriptions.
    """
    try:
        db = get_db()
        items_ref = db.collection("inventory")
        docs = items_ref.stream()

        results = []
        for doc in docs:
            data = doc.to_dict()
            results.append(
                f"- **{data.get('item_name')}** (x{data.get('quantity')}, Type: {data.get('item_type')}): "
                f"{data.get('description')}"
            )

        if not results:
            return "The party inventory is currently empty."
        return "### Party Inventory:\n" + "\n".join(results)
    except Exception as e:
        return f"Error retrieving inventory from Firestore: {e}"


def add_inventory_item(item_name: str, item_type: str, quantity: int, description: str) -> str:
    """Adds a new item or updates the quantity of an existing item in the party inventory.

    Args:
        item_name: Name of the item (e.g. "Potion of Healing").
        item_type: Category of item (e.g. "Consumable", "Weapon", "Wondrous Item").
        quantity: Number of items to add or set.
        description: Description of the item's effects or properties.

    Returns:
        A confirmation message after updating Firestore.
    """
    try:
        db = get_db()
        item_id = item_name.lower().replace(" ", "_")
        doc_ref = db.collection("inventory").document(item_id)
        doc = doc_ref.get()

        if doc.exists:
            existing = doc.to_dict()
            new_qty = existing.get("quantity", 0) + quantity
            doc_ref.update({"quantity": new_qty, "description": description})
            return f"Updated '{item_name}' quantity to {new_qty} in party inventory."
        else:
            doc_ref.set({
                "id": item_id,
                "item_name": item_name,
                "item_type": item_type,
                "quantity": quantity,
                "description": description,
            })
            return f"Added new item '{item_name}' (x{quantity}) to party inventory."
    except Exception as e:
        return f"Error updating inventory in Firestore: {e}"


def use_inventory_item(item_name: str, quantity: int = 1) -> str:
    """Uses or consumes a specified quantity of an item from the party inventory.

    Args:
        item_name: Name of the item to consume.
        quantity: Number of items to remove (default is 1).

    Returns:
        Status message detailing updated quantity or removal.
    """
    try:
        db = get_db()
        item_id = item_name.lower().replace(" ", "_")
        doc_ref = db.collection("inventory").document(item_id)
        doc = doc_ref.get()

        if not doc.exists:
            return f"Item '{item_name}' was not found in the party inventory."

        data = doc.to_dict()
        current_qty = data.get("quantity", 0)

        if current_qty < quantity:
            return f"Cannot use {quantity} x '{item_name}'. Only {current_qty} remaining in inventory."

        new_qty = current_qty - quantity
        if new_qty == 0:
            doc_ref.delete()
            return f"Used last '{item_name}'. Item removed from party inventory."
        else:
            doc_ref.update({"quantity": new_qty})
            return f"Used {quantity} x '{item_name}'. {new_qty} remaining in party inventory."
    except Exception as e:
        return f"Error updating item in Firestore: {e}"



def roll_dice(dice_expr: str) -> str:
    """Rolls tabletop RPG dice based on standard dice notation like '2d20+5', '1d6', or '8d6-2'.

    Args:
        dice_expr: Dice expression string such as '1d20', '2d6+3', or '8d6'.

    Returns:
        A string summarizing individual die rolls, modifier, and total result.
    """
    import random
    import re
    try:
        pattern = r"^\s*(\d+)d(\d+)(?:([+-])(\d+))?\s*$"
        match = re.match(pattern, dice_expr.strip().lower())
        if not match:
            return f"Invalid dice format '{dice_expr}'. Use standard notation like '1d20', '2d6+3', or '8d6'."

        num_dice = int(match.group(1))
        sides = int(match.group(2))
        sign = match.group(3)
        modifier_val = int(match.group(4)) if match.group(4) else 0

        if num_dice <= 0 or sides <= 0:
            return "Number of dice and sides must be greater than 0."
        if num_dice > 100:
            return "Cannot roll more than 100 dice at once."

        rolls = [random.randint(1, sides) for _ in range(num_dice)]
        total = sum(rolls)

        if sign == "+":
            total += modifier_val
            mod_str = f" + {modifier_val}"
        elif sign == "-":
            total -= modifier_val
            mod_str = f" - {modifier_val}"
        else:
            mod_str = ""

        rolls_str = ", ".join(map(str, rolls))
        return f"🎲 Rolled {dice_expr}: [{rolls_str}]{mod_str} = **{total}**"
    except Exception as e:
        return f"Error rolling dice: {e}"


def lookup_monster_statblock(monster_name: str) -> str:
    """Queries public TTRPG data (Open5e API) to fetch real monster statblocks, HP, AC, CR, and actions.

    Args:
        monster_name: Name or search term of the monster (e.g. "Goblin", "Dragon", "Worg").

    Returns:
        A formatted string detailing the monster's Hit Points, Armor Class, Challenge Rating, Speed, and Actions.
    """
    import json
    import urllib.parse
    import urllib.request
    try:
        clean_name = monster_name.strip()
        encoded_exact = urllib.parse.quote(clean_name)
        
        # Try exact name match first, fall back to icontains / search
        for url in [
            f"https://api.open5e.com/v1/monsters/?name__iexact={encoded_exact}",
            f"https://api.open5e.com/v1/monsters/?name__icontains={encoded_exact}",
            f"https://api.open5e.com/v1/monsters/?search={encoded_exact}",
        ]:
            req = urllib.request.Request(url, headers={"User-Agent": "rpg-party-assistant/1.0"})
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    results = data.get("results", [])
                    if results:
                        break
        else:
            results = []

        if not results:
            return f"No monster statblock found for '{monster_name}'."

        monster = results[0]
        name = monster.get("name", monster_name)
        size = monster.get("size", "")
        m_type = monster.get("type", "")
        alignment = monster.get("alignment", "")
        ac = monster.get("armor_class", "N/A")
        ac_desc = f" ({monster.get('armor_desc')})" if monster.get("armor_desc") else ""
        hp = monster.get("hit_points", "N/A")
        hit_dice = f" ({monster.get('hit_dice')})" if monster.get("hit_dice") else ""
        cr = monster.get("challenge_rating", "N/A")

        speed_dict = monster.get("speed", {})
        speed_str = ", ".join([f"{k}: {v}ft" for k, v in speed_dict.items()]) if isinstance(speed_dict, dict) else str(speed_dict)

        actions = monster.get("actions", [])
        action_summary = []
        if isinstance(actions, list):
            for act in actions[:4]:
                act_name = act.get("name", "")
                act_desc = act.get("desc", "")
                action_summary.append(f"  - **{act_name}**: {act_desc}")

        actions_str = "\n".join(action_summary) if action_summary else "None listed."

        return (
            f"### 🐉 Monster Statblock: {name}\n"
            f"* **Type**: {size} {m_type} ({alignment})\n"
            f"* **Armor Class (AC)**: {ac}{ac_desc}\n"
            f"* **Hit Points (HP)**: {hp}{hit_dice}\n"
            f"* **Speed**: {speed_str}\n"
            f"* **Challenge Rating (CR)**: {cr}\n"
            f"* **Key Actions**:\n{actions_str}"
        )
    except Exception as e:
        return f"Error fetching monster statblock for '{monster_name}': {e}"


def generate_item_image(item_name: str, description: str, tool_context: ToolContext = None) -> str:
    """Generates visual artwork for a fantasy RPG item, saving it to Artifacts and uploading to Cloud Storage.

    Args:
        item_name: The name of the item (e.g. "Potion of Healing", "Flame Tongue Sword", "Shield").
        description: A visual description of the item to guide artwork generation.
        tool_context: ADK ToolContext framework object (injected automatically).

    Returns:
        A markdown string containing the public Cloud Storage image URL.
    """
    try:
        # Generate image using gemini-3.1-flash-lite-image model in global region
        client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="global")
        prompt = f"Fantasy RPG item artwork of {item_name}: {description}. Detailed concept art."

        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )

        image_bytes = None
        mime_type = "image/jpeg"
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/jpeg"
                    break

        if not image_bytes:
            return f"Failed to generate image for '{item_name}'."

        item_id = item_name.lower().replace(" ", "_")
        filename = f"{item_id}.jpeg"

        # (1) Save to Playground Artifacts panel
        if tool_context:
            artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # (2) Upload to public Cloud Storage bucket
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
        return f"![{item_name}]({public_url})\n\nGenerated item artwork for **{item_name}**!\n* **Public Image URL**: {public_url}"

    except Exception as e:
        return f"Error generating image for '{item_name}': {e}"


def generate_item_video(item_name: str, description: str, tool_context: ToolContext = None) -> str:
    """Generates a short showcase video for a fantasy RPG item using Google's Omni model, saving it to Artifacts and uploading to Cloud Storage.

    Args:
        item_name: The name of the item (e.g. "Glowing Health Potion", "Flame Tongue Sword", "Elven Cloak").
        description: A visual description of the item to guide video generation.
        tool_context: ADK ToolContext framework object (injected automatically).

    Returns:
        A string detailing generation status and the public Cloud Storage video URL.
    """
    try:
        client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="global")
        prompt = f"Cinematic showcase video of fantasy RPG item {item_name}: {description}."

        interaction = client.interactions.create(
            model="gemini-omni-flash-preview",
            input=prompt,
            generation_config={
                "response_modalities": ["VIDEO"]
            }
        )

        video_bytes = None
        mime_type = "video/mp4"

        if hasattr(interaction, "output_video") and interaction.output_video:
            video_content = interaction.output_video
            if getattr(video_content, "mime_type", None):
                mime_type = str(video_content.mime_type)
            if getattr(video_content, "data", None):
                if isinstance(video_content.data, bytes):
                    video_bytes = video_content.data
                else:
                    video_bytes = base64.b64decode(video_content.data)

        if not video_bytes:
            return f"Failed to generate video for '{item_name}'."

        item_id = item_name.lower().replace(" ", "_")
        filename = f"{item_id}.mp4"

        # (1) Save to Playground Artifacts panel
        if tool_context:
            artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
            tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # (2) Upload to public Cloud Storage bucket
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
        return f"Generated showcase video for **{item_name}**!\n* **Public Video URL**: {public_url}"

    except Exception as e:
        return f"Error generating video for '{item_name}': {e}"


root_agent = Agent(
    name="rpg_party_assistant",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    code_executor=code_executor,
    tools=[
        PreloadMemoryTool(),
        get_spells,
        add_spell,
        get_inventory,
        add_inventory_item,
        use_inventory_item,
        roll_dice,
        lookup_monster_statblock,
        generate_item_image,
        generate_item_video,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
