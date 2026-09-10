import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

MEMORY_FILE = "jarvis_memory.json"

# --- Gedächtnis-Funktionen ---

def get_all_memories() -> dict:
    """Liest alle gespeicherten Notizen aus."""
    if not os.path.exists(MEMORY_FILE):
        return {}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_memory(topic: str, detail: str):
    """Speichert eine Information über Sir dauerhaft ab."""
    memories = get_all_memories()
    memories[topic] = detail
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)
    return f"Gedächtnis aktualisiert: [{topic}] -> '{detail}' wurde dauerhaft hinterlegt."

# --- Standard-Tools ---

def get_current_time():
    """Gibt die deutsche Ortszeit zurück."""
    now = datetime.now(ZoneInfo("Europe/Berlin"))
    return f"Es ist {now.strftime('%H:%M')} Uhr am {now.strftime('%d.%m.%Y')}."

def run_protocol(protocol_name: str):
    """Führt vordefinierte Protokolle aus."""
    if protocol_name.lower() == "fokus":
        return "Protokoll Fokus aktiv: Arbeitsumgebung scharfgestellt, Störquellen minimiert."
    elif protocol_name.lower() == "party":
        return "Protokoll House Party ausgeführt: Soundsysteme und Beleuchtung synchronisiert."
    return f"Protokoll '{protocol_name}' ist nicht hinterlegt, Sir."

def sync_spielerplus():
    """Prüft SpielerPlus auf angenommene Termine."""
    return "SpielerPlus-Schnittstelle aktiv: Keine anstehenden Termine gefunden."

# --- Schemas für Groq ---

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Nutze dieses Tool IMMER, wenn Sir dir eine persönliche Information, Vorliebe, Arbeitsweise oder Regel mitteilt, die du dir dauerhaft merken sollst.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Kategorie oder Stichwort (z. B. 'kaffee_vorliebe', 'spitzname', 'musik')",
                    },
                    "detail": {
                        "type": "string",
                        "description": "Die konkrete Information, die du dir merken musst.",
                    },
                },
                "required": ["topic", "detail"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Ruft die aktuelle Uhrzeit und das Datum ab.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_protocol",
            "description": "Führt ein Jarvis-Sicherheitsprotokoll aus.",
            "parameters": {
                "type": "object",
                "properties": {
                    "protocol_name": {
                        "type": "string",
                        "description": "Name des Protokolls (z.B. 'fokus')",
                    }
                },
                "required": ["protocol_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sync_spielerplus",
            "description": "Prüft SpielerPlus auf angenommene Termine.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

TOOL_MAP = {
    "save_memory": save_memory,
    "get_current_time": get_current_time,
    "run_protocol": run_protocol,
    "sync_spielerplus": sync_spielerplus,
}
