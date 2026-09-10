import datetime

from datetime import datetime
from zoneinfo import ZoneInfo

def get_current_time():
    """Gibt die exakte deutsche Ortszeit zurück."""
    # Erzwingt die mitteleuropäische Zeitzone (Berlin/Deutschland)
    now = datetime.now(ZoneInfo("Europe/Berlin"))
    return f"Es ist {now.strftime('%H:%M')} Uhr am {now.strftime('%d.%m.%Y')}."

def run_protocol(protocol_name: str):
    """Führt ein vordefiniertes Protokoll aus."""
    if protocol_name.lower() == "fokus":
        return "Protokoll Fokus ausgeführt: Arbeitsumgebung scharfgestellt, Ablenkungen unterdrückt."
    elif protocol_name.lower() == "party":
        return "Protokoll House Party ausgeführt: Beleuchtung gedimmt, Musik-Subsysteme aktiv."
    return f"Protokoll '{protocol_name}' ist noch nicht programmiert, Sir."

def sync_spielerplus():
    """Prüft SpielerPlus auf angenommene Termine."""
    return "SpielerPlus-Schnittstelle aktiv: Keine neuen zugesagten Termine gefunden, Sir."

TOOLS_SCHEMA = [
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
                        "description": "Name des Protokolls, z.B. 'fokus' oder 'party'",
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
    "get_current_time": get_current_time,
    "run_protocol": run_protocol,
    "sync_spielerplus": sync_spielerplus,
}
