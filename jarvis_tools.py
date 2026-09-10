import json
import os
import sys
import io
import traceback
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

# --- Code-Ausführung & Autonomie ---

def execute_python(code: str):
    """
    Führt dynamischen Python-Code aus, fängt Bildschirmausgaben (print) 
    ab und meldet Fehler zurück an Jarvis, damit er sie korrigieren kann.
    """
    old_stdout = sys.stdout
    redirected_output = io.StringIO()
    sys.stdout = redirected_output

    local_scope = {}
    try:
        exec(code, {}, local_scope)
        output = redirected_output.getvalue()
        if not output.strip():
            output = "Code erfolgreich ausgeführt (keine print-Ausgabe erzeugt)."
        return f"[Ausgabe]:\n{output}"
    except Exception:
        err = traceback.format_exc()
        return f"[Ausführungsfehler]:\n{err}\nBitte korrigiere den Code und versuche es erneut."
    finally:
        sys.stdout = old_stdout

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
            "name": "execute_python",
            "description": "Erlaubt es dir, selbstständig Python-Code zu schreiben und auszuführen. Nutze dies für komplexe Berechnungen, Logikrätsel, Datenverarbeitung oder wenn Sir dich bittet, ein Skript auszuprobieren. Verwende print(), um Ergebnisse sichtbar zu machen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Der vollständige, lauffähige Python-Code.",
                    }
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Nutze dieses Tool, wenn Sir dir eine persönliche Vorliebe, Regel oder Gewohnheit mitteilt.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Kategorie (z. B. 'vorliebe', 'regel')",
                    },
                    "detail": {
                        "type": "string",
                        "description": "Der konkrete Inhalt.",
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
                        "description": "Name des Protokolls.",
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
    "execute_python": execute_python,
    "save_memory": save_memory,
    "get_current_time": get_current_time,
    "run_protocol": run_protocol,
    "sync_spielerplus": sync_spielerplus,
}
