import json
import os
import sys
import io
import traceback
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build

MEMORY_FILE = "jarvis_memory.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# --- Google Calendar Verbindung ---

def get_calendar_service():
    """Initialisiert den Google Calendar Client über das Dienstkonto."""
    raw_creds = st.secrets.get("GOOGLE_SERVICE_ACCOUNT")
    if not raw_creds:
        return None
    try:
        creds_dict = json.loads(raw_creds) if isinstance(raw_creds, str) else dict(raw_creds)
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        return build("calendar", "v3", credentials=creds)
    except Exception:
        return None

def list_calendar_events(days_ahead: int = 7):
    """Liest anstehende Termine aus Sirs Google Kalender aus."""
    service = get_calendar_service()
    cal_id = st.secrets.get("GOOGLE_CALENDAR_ID")
    if not service or not cal_id:
        return "Kalender-Schnittstelle nicht konfiguriert. Prüfe Secrets in Streamlit."

    now = datetime.now(ZoneInfo("Europe/Berlin"))
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days_ahead)).isoformat()

    try:
        events_result = service.events().list(
            calendarId=cal_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = events_result.get("items", [])
        if not events:
            return f"Keine anstehenden Termine in den nächsten {days_ahead} Tagen gefunden."

        result_lines = [f"Termine der nächsten {days_ahead} Tage:"]
        for ev in events:
            summary = ev.get("summary", "Ohne Titel")
            start = ev["start"].get("dateTime", ev["start"].get("date"))
            dt = datetime.fromisoformat(start)
            result_lines.append(f"- {dt.strftime('%d.%m.%Y um %H:%M Uhr')}: {summary}")

        return "\n".join(result_lines)
    except Exception as e:
        return f"Fehler beim Abrufen des Kalenders: {e}"

def create_calendar_event(summary: str, start_time: str, end_time: str = None, description: str = ""):
    """
    Erstellt einen neuen Kalendereintrag.
    Format für start_time und end_time: YYYY-MM-DDTHH:MM:SS (z. B. '2026-09-12T18:00:00').
    """
    service = get_calendar_service()
    cal_id = st.secrets.get("GOOGLE_CALENDAR_ID")
    if not service or not cal_id:
        return "Kalender-Schnittstelle nicht konfiguriert. Prüfe Secrets in Streamlit."

    try:
        if not end_time:
            start_dt = datetime.fromisoformat(start_time)
            end_time = (start_dt + timedelta(hours=1)).isoformat()

        event_body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_time, "timeZone": "Europe/Berlin"},
            "end": {"dateTime": end_time, "timeZone": "Europe/Berlin"},
        }

        service.events().insert(calendarId=cal_id, body=event_body).execute()
        return f"Termin '{summary}' am {start_time} erfolgreich in Ihren Google Kalender eingetragen."
    except Exception as e:
        return f"Fehler beim Erstellen des Termins: {e}"

# --- Gedächtnis & Code-Tools ---

def get_all_memories() -> dict:
    if not os.path.exists(MEMORY_FILE):
        return {}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_memory(topic: str, detail: str):
    memories = get_all_memories()
    memories[topic] = detail
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)
    return f"Gedächtnis aktualisiert: [{topic}] -> '{detail}' wurde dauerhaft hinterlegt."

def execute_python(code: str):
    old_stdout = sys.stdout
    redirected = io.StringIO()
    sys.stdout = redirected
    try:
        exec(code, {}, {})
        output = redirected.getvalue()
        return f"[Ausgabe]:\n{output}" if output.strip() else "Erfolgreich ausgeführt."
    except Exception:
        return f"[Fehler]:\n{traceback.format_exc()}"
    finally:
        sys.stdout = old_stdout

def get_current_time():
    now = datetime.now(ZoneInfo("Europe/Berlin"))
    return f"Es ist {now.strftime('%H:%M')} Uhr am {now.strftime('%d.%m.%Y')}."

def run_protocol(protocol_name: str):
    p = protocol_name.lower()
    if "fokus" in p:
        return "Protokoll Fokus aktiv: Arbeitsumgebung scharfgestellt, Störquellen minimiert."
    elif "party" in p:
        return "Protokoll House Party ausgeführt: Soundsysteme und Beleuchtung synchronisiert."
    elif any(x in p for x in ["ruhe", "schlaf", "sleep", "standby"]):
        return "TRIGGER_SLEEP_MODE: Ruhemodus initiiert. Bestätige Sir den Ruhemodus kurz und loyal in einem Satz. Alle Mikrofone und Sensoren werden danach heruntergefahren."
    return f"Protokoll '{protocol_name}' ist nicht hinterlegt, Sir."

def sync_spielerplus():
    return "SpielerPlus-Schnittstelle wird zu einem späteren Zeitpunkt konfiguriert."

# --- Schemas für Groq ---

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "list_calendar_events",
            "description": "Ruft Termine aus Sirs Google Kalender ab. Nutze dies bei Fragen wie 'Was steht an?', 'Welche Termine habe ich diese Woche?' oder 'Habe ich heute Zeit?'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": "Anzahl der Tage in die Zukunft (Standard ist 7).",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Erstellt einen neuen Termin im Google Kalender von Sir. Zeitformat muss ISO-Format sein: YYYY-MM-DDTHH:MM:SS (z.B. '2026-09-15T14:30:00').",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Titel des Termins.",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Startzeitpunkt im ISO-Format.",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "Endzeitpunkt im ISO-Format (optional).",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optionale Notiz zum Termin.",
                    },
                },
                "required": ["summary", "start_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_python",
            "description": "Führt dynamischen Python-Code aus.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python-Code."}
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Speichert persönliche Informationen und Vorlieben von Sir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "detail": {"type": "string"},
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
            "description": "Führt ein Jarvis-Protokoll aus. Verfügbare Protokolle: 'fokus', 'party', 'ruhemodus' (schaltet Sensoren und Mikrofon ab und versetzt Jarvis in den Ruhezustand).",
            "parameters": {
                "type": "object",
                "properties": {
                    "protocol_name": {
                        "type": "string",
                        "description": "Name des Protokolls: 'fokus', 'party' oder 'ruhemodus'.",
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
            "description": "Prüft SpielerPlus auf Termine.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

TOOL_MAP = {
    "list_calendar_events": list_calendar_events,
    "create_calendar_event": create_calendar_event,
    "execute_python": execute_python,
    "save_memory": save_memory,
    "get_current_time": get_current_time,
    "run_protocol": run_protocol,
    "sync_spielerplus": sync_spielerplus,
}
