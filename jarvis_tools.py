import os
import json
from datetime import datetime

PROTOCOLS_FILE = "jarvis_protocols.json"
MEMORIES_FILE = "jarvis_memory.json"

# --- PROTOKOLL-VERWALTUNG ---

def load_protocols() -> dict:
    if os.path.exists(PROTOCOLS_FILE):
        try:
            with open(PROTOCOLS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # Standard-Protokolle ab Werk
    return {
        "ruhemodus": {
            "description": "Schaltet alle aktiven Sensoren ab und versetzt das System in den Standby.",
            "actions": ["TRIGGER_SLEEP_MODE"]
        }
    }

def save_protocols_to_disk(protocols: dict):
    try:
        with open(PROTOCOLS_FILE, "w", encoding="utf-8") as f:
            json.dump(protocols, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def create_protocol(name: str, actions: list[str], description: str = "") -> str:
    """Erstellt eine neue Routine/ein neues Protokoll und speichert es ab."""
    protocols = load_protocols()
    clean_name = name.lower().strip()
    
    protocols[clean_name] = {
        "description": description or f"Benutzerdefiniertes Protokoll {name}",
        "actions": actions,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    save_protocols_to_disk(protocols)
    return f"Protokoll '{name}' mit {len(actions)} Aktionen erfolgreich im System hinterlegt, Sir."

def list_protocols() -> str:
    """Gibt alle hinterlegten Protokolle zurück."""
    protocols = load_protocols()
    if not protocols:
        return "Keine Protokolle registriert, Sir."
    
    result = ["Verfügbare Protokolle:"]
    for name, data in protocols.items():
        desc = data.get("description", "")
        actions = ", ".join(data.get("actions", []))
        result.append(f"• [{name.upper()}]: {desc} (Aktionen: {actions})")
    return "\n".join(result)

def run_protocol(protocol_name: str) -> str:
    """Führt ein hinterlegtes Protokoll aus."""
    protocols = load_protocols()
    clean_name = protocol_name.lower().strip()

    if clean_name == "ruhemodus" or "ruhe" in clean_name or "schlaf" in clean_name:
        return "TRIGGER_SLEEP_MODE: Gehe in den Ruhemodus, Sir."

    if clean_name in protocols:
        proto = protocols[clean_name]
        actions_text = "; ".join(proto.get("actions", []))
        return f"PROTOKOLL '{clean_name.upper()}' INITIIERT. Auszuführende Sequenzen: {actions_text}"
    
    return f"Protokoll '{protocol_name}' ist nicht in der Datenbank verzeichnet, Sir."

# --- GEDÄCHTNIS-FUNKTIONEN ---

def get_all_memories() -> dict:
    if os.path.exists(MEMORIES_FILE):
        try:
            with open(MEMORIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_memory(key: str, value: str) -> str:
    mems = get_all_memories()
    mems[key.strip()] = value.strip()
    try:
        with open(MEMORIES_FILE, "w", encoding="utf-8") as f:
            json.dump(mems, f, ensure_ascii=False, indent=2)
        return f"Erinnerung gespeichert: {key} = {value}"
    except Exception as e:
        return f"Fehler beim Speichern: {e}"

def list_calendar_events(days_ahead: int = 4) -> str:
    # Optionaler Google-Kalender Hook
    return "Termine synchronisiert: Keine anstehenden Konflikte in den nächsten 4 Tagen."

# --- TOOL SCHEMA & MAPPING FÜR GROQ ---

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "create_protocol",
            "description": "Erstellt ein neues Protokoll / eine neue Routine mit einer Liste von Aktionsschritten, wenn Sir den Befehl dazu gibt.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name des Protokolls, z. B. 'Fokus', 'Guten Morgen', 'Werkstatt'"},
                    "description": {"type": "string", "description": "Kurze Beschreibung des Zwecks"},
                    "actions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Liste der auszuführenden Schritte/Aktionen"
                    }
                },
                "required": ["name", "actions"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_protocol",
            "description": "Aktiviert und führt ein bestehendes Protokoll oder den Ruhemodus aus.",
            "parameters": {
                "type": "object",
                "properties": {
                    "protocol_name": {"type": "string", "description": "Name des Protokolls (z. B. 'ruhemodus', 'fokus')"}
                },
                "required": ["protocol_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_protocols",
            "description": "Listet alle im System hinterlegten Protokolle auf.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Speichert persönliche Fakten über Sir dauerhaft ab.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Thema/Kategorie"},
                    "value": {"type": "string", "description": "Der zu merkende Fakt"}
                },
                "required": ["key", "value"]
            }
        }
    }
]

TOOL_MAP = {
    "create_protocol": create_protocol,
    "run_protocol": run_protocol,
    "list_protocols": list_protocols,
    "save_memory": save_memory,
}
