import os
import json
import asyncio
import base64
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st
import streamlit.components.v1 as components
from groq import Groq
import edge_tts
from jarvis_tools import TOOLS_SCHEMA, TOOL_MAP, get_all_memories, list_calendar_events

st.set_page_config(page_title="J.A.R.V.I.S. HUD", page_icon="🤖", layout="wide")

# --- Futuristische Sci-Fi Stylesheet mit flexiblen Overlays ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700;900&family=Rajdhani:wght@500;600;700&display=swap');

    .stApp {
        background-color: #020813;
        background-image: 
            radial-gradient(circle at 50% 45%, rgba(0, 240, 255, 0.08) 0%, transparent 70%),
            linear-gradient(rgba(0, 240, 255, 0.035) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0, 240, 255, 0.035) 1px, transparent 1px);
        background-size: 100% 100%, 32px 32px, 32px 32px;
        color: #cffafe;
        font-family: 'Rajdhani', sans-serif;
    }

    /* LINKE SIDEBAR ALS OVERLAY: Schiebt den Hauptinhalt nicht mehr zur Seite */
    section[data-testid="stSidebar"] {
        position: absolute !important;
        z-index: 99999 !important;
        height: 100vh !important;
        background: rgba(3, 14, 28, 0.97) !important;
        border-right: 1px solid rgba(0, 240, 255, 0.35) !important;
        box-shadow: 10px 0 35px rgba(0, 0, 0, 0.85) !important;
    }
    
    /* Hauptcontainer erzwingt volle Breite, damit HUD immer zu 100% mittig bleibt */
    section.main {
        margin-left: 0 !important;
        width: 100% !important;
    }

    /* RECHTES OVERLAY-FENSTER (Protokoll - exakt wie links) */
    .right-drawer-overlay {
        position: fixed !important;
        top: 0 !important;
        right: 0 !important;
        width: 360px !important;
        max-width: 90vw !important;
        height: 100vh !important;
        background: rgba(3, 14, 28, 0.97) !important;
        border-left: 1px solid rgba(0, 240, 255, 0.35) !important;
        box-shadow: -10px 0 35px rgba(0, 0, 0, 0.85) !important;
        backdrop-filter: blur(16px) !important;
        z-index: 99999 !important;
        padding: 24px 18px !important;
        overflow-y: auto !important;
        animation: slideInRight 0.3s cubic-bezier(0.16, 1, 0.3, 1) !important;
    }

    @keyframes slideInRight {
        from { transform: translateX(100%); }
        to { transform: translateX(0); }
    }

    /* Sci-Fi HUD Kacheln */
    .hud-card {
        background: rgba(4, 19, 36, 0.75);
        border: 1px solid rgba(0, 240, 255, 0.4);
        box-shadow: 0 0 16px rgba(0, 240, 255, 0.08) inset, 0 0 10px rgba(0, 240, 255, 0.05);
        clip-path: polygon(0 0, calc(100% - 14px) 0, 100% 14px, 100% 100%, 14px 100%, 0 calc(100% - 14px));
        padding: 14px 18px;
        margin-bottom: 14px;
        backdrop-filter: blur(8px);
        position: relative;
    }

    .hud-card::before {
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        width: 8px;
        height: 8px;
        border-top: 2px solid #00f0ff;
        border-left: 2px solid #00f0ff;
    }

    .hud-header {
        font-family: 'Orbitron', monospace;
        font-size: 11px;
        letter-spacing: 2px;
        color: #38bdf8;
        text-transform: uppercase;
        margin-bottom: 8px;
        border-bottom: 1px solid rgba(56, 189, 248, 0.2);
        padding-bottom: 4px;
        display: flex;
        justify-content: space-between;
    }
</style>
""", unsafe_allow_html=True)

CHAT_FILE = "chat_history.json"

def load_chat_history():
    if os.path.exists(CHAT_FILE):
        try:
            with open(CHAT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_chat_history(messages):
    try:
        with open(CHAT_FILE, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

raw_key = st.secrets.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY", "")
GROQ_API_KEY = raw_key.strip() if raw_key else ""
if not GROQ_API_KEY:
    st.error("API-Key fehlt! Bitte in den Secrets hinterlegen.")
    st.stop()

client = Groq(api_key=GROQ_API_KEY)

@st.cache_data(ttl=3600)
def get_available_models():
    try:
        models_data = client.models.list()
        chat_models = [m.id for m in models_data.data if "whisper" not in m.id.lower()]
        return sorted(chat_models)
    except Exception as e:
        return []

available_models = get_available_models()

def build_system_prompt():
    memories = get_all_memories()
    mem_text = "\n".join([f"- {k}: {v}" for k, v in memories.items()]) if memories else "Keine Einträge vorhanden."
    
    return f"""Du bist J.A.R.V.I.S., die hochentwickelte KI von Sir.
1. Sprich den Nutzer stets diskret und loyal mit 'Sir' an.
2. SPRACHE: Antworte IMMER exakt in der Sprache, in der Sir dich anspricht.
3. Sei präzise, loyal, trocken-humorvoll und halte dich extrem kurz (1-2 Sätze).
4. Gib niemals interne Denkprozesse oder Meta-Kommentare aus.
5. Wenn Sir dir befiehlt schlafen zu gehen, rufe SOFORT 'run_protocol' mit protocol_name='ruhemodus' auf.
6. Wenn Sir dir Fakten über sich mitteilt, rufe sofort 'save_memory' auf.

Dauerhaftes Gedächtnis über Sir:
{mem_text}
"""

if "messages" not in st.session_state:
    saved = load_chat_history()
    if saved:
        saved[0] = {"role": "system", "content": build_system_prompt()}
        st.session_state.messages = saved
    else:
        st.session_state.messages = [{"role": "system", "content": build_system_prompt()}]

if "latest_audio_b64" not in st.session_state:
    st.session_state.latest_audio_b64 = ""

if "sleep_mode" not in st.session_state:
    st.session_state.sleep_mode = False

if "show_protocol" not in st.session_state:
    st.session_state.show_protocol = False

# --- LINKE SIDEBAR ---
with st.sidebar:
    st.markdown("<h3 style='font-family: Orbitron; color: #00f0ff;'>⚙️ SYSTEM CONTROL</h3>", unsafe_allow_html=True)
    
    if st.session_state.sleep_mode:
        st.warning("🌙 RUHEMODUS AKTIV")
        if st.button("⚡ MANUELL AUFWECKEN"):
            st.session_state.sleep_mode = False
            st.rerun()
        enable_tts = False
    else:
        enable_tts = st.toggle("🔊 Sprachausgabe erlauben", value=True)

    input_lang = st.selectbox("Mikrofon-Sprache:", ["Deutsch (de-DE)", "English (en-US)"])
    rec_lang_code = "de-DE" if "Deutsch" in input_lang else "en-US"

    st.divider()
    st.markdown("<h4 style='font-family: Orbitron; font-size: 13px; color: #38bdf8;'>🧠 LANGZEITGEDÄCHTNIS</h4>", unsafe_allow_html=True)
    mems = get_all_memories()
    if mems:
        for k, v in mems.items():
            st.markdown(f"<div style='font-size: 12px; margin-bottom: 4px;'>• <b style='color:#38bdf8;'>{k}:</b> {v}</div>", unsafe_allow_html=True)
    else:
        st.caption("Noch keine Einträge vorhanden.")

    st.divider()
    st.markdown("<h4 style='font-family: Orbitron; font-size: 13px; color: #38bdf8;'>KI-KERN (GROQ)</h4>", unsafe_allow_html=True)
    if available_models:
        target_model = "openai/gpt-oss-120b"
        default_idx = available_models.index(target_model) if target_model in available_models else 0
        MODEL_NAME = st.selectbox("Aktives Modell:", available_models, index=default_idx)
    else:
        st.error("Keine Modelle gefunden.")
        st.stop()

    if st.button("🗑️ Chat-Verlauf leeren"):
        if os.path.exists(CHAT_FILE):
            os.remove(CHAT_FILE)
        st.session_state.messages = [{"role": "system", "content": build_system_prompt()}]
        st.session_state.latest_audio_b64 = ""
        st.session_state.sleep_mode = False
        st.rerun()

def detect_language(text: str) -> str:
    lower = text.lower()
    if any(c in lower for c in "äöüß"): return "de"
    return "en"

async def generate_edge_voice(text: str, voice_name: str, rate: str = "-3%", pitch: str = "-4Hz") -> bytes:
    communicate = edge_tts.Communicate(text=text, voice=voice_name, rate=rate, pitch=pitch)
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    return audio_data

def generate_voice_audio(text: str) -> bytes:
    lang = detect_language(text)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    if lang == "de":
        return loop.run_until_complete(generate_edge_voice(text, "de-DE-KillianNeural", rate="-3%", pitch="-4Hz"))
    else:
        return loop.run_until_complete(generate_edge_voice(text, "en-GB-RyanNeural", rate="-2%", pitch="-2Hz"))

def process_query(user_text, is_voice=False):
    lower_in = user_text.lower()
    if st.session_state.sleep_mode:
        if any(w in lower_in for w in ["aufwachen", "wach auf", "wake up"]):
            st.session_state.sleep_mode = False

    st.session_state.messages[0] = {"role": "system", "content": build_system_prompt()}
    st.session_state.messages.append({"role": "user", "content": user_text})

    try:
        req_params = {
            "model": MODEL_NAME,
            "messages": st.session_state.messages,
            "tools": TOOLS_SCHEMA,
            "tool_choice": "auto",
            "temperature": 0.5,
        }
        if "gpt-oss" in MODEL_NAME:
            req_params["extra_body"] = {"include_reasoning": False}

        response = client.chat.completions.create(**req_params)
        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls
        triggered_sleep = False

        if tool_calls:
            clean_tool_calls = [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in tool_calls]
            st.session_state.messages.append({"role": "assistant", "content": response_message.content or "", "tool_calls": clean_tool_calls})

            for tool_call in tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                function_output = TOOL_MAP.get(func_name, lambda **x: "Funktion nicht verfügbar")(**func_args)

                if "TRIGGER_SLEEP_MODE" in str(function_output):
                    triggered_sleep = True

                st.session_state.messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": func_name, "content": str(function_output)})

            second_params = {"model": MODEL_NAME, "messages": st.session_state.messages}
            if "gpt-oss" in MODEL_NAME:
                second_params["extra_body"] = {"include_reasoning": False}

            second_response = client.chat.completions.create(**second_params)
            reply = second_response.choices[0].message.content
        else:
            reply = response_message.content

        if reply and "</think>" in reply: reply = reply.split("</think>")[-1].strip()
        if reply and "Thus final." in reply: reply = reply.split("Thus final.")[-1].strip()

        st.session_state.messages.append({"role": "assistant", "content": reply})
        save_chat_history(st.session_state.messages)

        if triggered_sleep:
            st.session_state.sleep_mode = True

        if (is_voice or triggered_sleep) and (enable_tts or triggered_sleep) and reply:
            audio_bytes = generate_voice_audio(reply)
            st.session_state.latest_audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        else:
            st.session_state.latest_audio_b64 = ""

    except Exception as e:
        st.error(f"Fehler: {e}")

# --- SCHALTER FÜR DAS RECHTE PROTOKOLL-FENSTER (Oben rechts im Eck) ---
col_empty, col_btn = st.columns([9.2, 0.8])
with col_btn:
    if not st.session_state.show_protocol:
        if st.button("🗨️ PROTOKOLL", use_container_width=True):
            st.session_state.show_protocol = True
            st.rerun()

# --- RECHTES PROTOKOLL-OVERLAY (Sicherer Inject-Trick ohne Layout-Bruch) ---
if st.session_state.show_protocol:
    proto_container = st.container()
    with proto_container:
        # Dieser kleine Script-Block verwandelt das aktuelle Container-Div in das rechte Sidebar-Overlay
        components.html("""
        <script>
            const frame = window.frameElement;
            if (frame) {
                const block = frame.closest('div[data-testid="stVerticalBlock"]');
                if (block) { block.classList.add('right-drawer-overlay'); }
            }
        </script>
        """, height=0, width=0)
        
        h_col1, h_col2 = st.columns([0.8, 0.2])
        with h_col1:
            st.markdown("<h3 style='font-family: Orbitron; color: #00f0ff; margin:0;'>💬 PROTOKOLL</h3>", unsafe_allow_html=True)
        with h_col2:
            if st.button("✖", key="close_protocol_btn"):
                st.session_state.show_protocol = False
                st.rerun()
        st.divider()

        chat_history_container = st.container(height=650)
        with chat_history_container:
            for msg in st.session_state.messages[1:]:
                role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
                content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
                if role in ["user", "assistant"] and content:
                    with st.chat_message(role):
                        st.write(content)

# --- FEST SYMMETRISCHES HUD-LAYOUT ---
col_left, col_center, col_right = st.columns([3.2, 5.6, 3.2])

# === LINKE SPALTE: ECHTZEIT & KALENDER ===
with col_left:
    components.html("""
    <div style="
        background: rgba(4, 19, 36, 0.75);
        border: 1px solid rgba(0, 240, 255, 0.4);
        box-shadow: 0 0 16px rgba(0, 240, 255, 0.08) inset;
        clip-path: polygon(0 0, calc(100% - 14px) 0, 100% 14px, 100% 100%, 14px 100%, 0 calc(100% - 14px));
        padding: 14px 18px;
        font-family: 'Rajdhani', sans-serif;
        color: #cffafe;
    ">
        <div style="font-family: 'Orbitron', monospace; font-size: 11px; letter-spacing: 2px; color: #38bdf8; text-transform: uppercase; margin-bottom: 8px; border-bottom: 1px solid rgba(56, 189, 248, 0.2); padding-bottom: 4px; display: flex; justify-content: space-between;">
            <span>⏱️ CHRONO // SYSTEM</span> <span>[LIVE]</span>
        </div>
        <div id="chrono-clock" style="font-family: 'Orbitron', monospace; font-size: 26px; font-weight: 700; color: #00f0ff; text-shadow: 0 0 12px rgba(0, 240, 255, 0.7);">--:--:--</div>
        <div id="chrono-date" style="color: #38bdf8; font-size: 14px; font-weight: 600; margin-top: 4px;">--</div>
        <div style="font-size: 11px; color: #64748b; margin-top: 2px;">TIMEZONE: EUROPE/BERLIN</div>
    </div>

    <script>
    function updateClock() {
        const now = new Date();
        const timeStr = now.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        const options = { weekday: 'long', year: 'numeric', month: '2-digit', day: '2-digit' };
        const dateStr = now.toLocaleDateString('de-DE', options);
        
        const clockEl = document.getElementById('chrono-clock');
        const dateEl = document.getElementById('chrono-date');
        if (clockEl) clockEl.innerText = timeStr;
        if (dateEl) dateEl.innerText = dateStr;
    }
    setInterval(updateClock, 1000);
    updateClock();
    </script>
    """, height=130)

    cal_preview = list_calendar_events(days_ahead=4)
    first_lines = "\n".join(cal_preview.split("\n")[:4]) if isinstance(cal_preview, str) else "Keine Termine"
    st.markdown(f"""
    <div class="hud-card">
        <div class="hud-header"><span>📅 KALENDER // AGENDA</span> <span>[SYNC]</span></div>
        <div style="font-size: 13px; line-height: 1.6; color: #7dd3fc; white-space: pre-line;">{first_lines}</div>
    </div>
    """, unsafe_allow_html=True)


# === MITTLERE SPALTE: REINES HOLOGRAMM (KOMPLETT OHNE TEXT) ===
with col_center:
    audio_payload = st.session_state.latest_audio_b64
    st.session_state.latest_audio_b64 = ""
    is_sleep = st.session_state.sleep_mode

    hud_template = """
    <div style="position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; width: 100%;">
        
        <!-- Winziges, unsichtbares Mikrofon-Icon oben rechts (ohne Border, ohne Background) -->
        <div style="position: absolute; top: 0px; right: 20px; z-index: 10;">
            <button id="btn-hud-mic" onclick="toggleHudMic()" style="
                background: transparent;
                border: none;
                outline: none;
                cursor: pointer;
                padding: 8px;
                opacity: 0.6;
                transition: all 0.3s ease;
            " title="Mikrofon stummschalten / aktivieren">
                <svg id="svg-mic-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#00f0ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path>
                    <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                    <line x1="12" y1="19" x2="12" y2="22"></line>
                    <line id="mic-slash-line" x1="2" y1="2" x2="22" y2="22" stroke="#ef4444" stroke-width="2.5" style="display: none;"></line>
                </svg>
            </button>
        </div>

        <!-- Arc Reactor Hologramm (Komplett ohne jegliche Text-Badges!) -->
        <div id="reactor-wrapper" onclick="triggerListenDirectly()" style="cursor: pointer; position: relative; width: 340px; height: 340px; display: flex; align-items: center; justify-content: center;" title="Klicken für Sofortbefehl">
            <svg id="arc-reactor" viewBox="0 0 400 400" width="340" height="340">
                <line x1="200" y1="10" x2="200" y2="35" stroke="var(--hud-stroke, #00f0ff)" stroke-width="2" opacity="0.6" />
                <line x1="200" y1="365" x2="200" y2="390" stroke="var(--hud-stroke, #00f0ff)" stroke-width="2" opacity="0.6" />
                <line x1="10" y1="200" x2="35" y2="200" stroke="var(--hud-stroke, #00f0ff)" stroke-width="2" opacity="0.6" />
                <line x1="365" y1="200" x2="390" y2="200" stroke="var(--hud-stroke, #00f0ff)" stroke-width="2" opacity="0.6" />

                <circle cx="200" cy="200" r="186" fill="none" stroke="rgba(0, 240, 255, 0.15)" stroke-width="1.5" />
                <circle cx="200" cy="200" r="176" fill="none" stroke="rgba(0, 240, 255, 0.25)" stroke-dasharray="2, 6" />

                <g id="ring-outer-blocks" style="transform-origin: 200px 200px; animation: spinClockwise var(--spin-outer, 32s) linear infinite;">
                    <circle cx="200" cy="200" r="156" fill="none" stroke="var(--hud-stroke, #00f0ff)" stroke-width="10" stroke-dasharray="60, 25, 40, 20, 80, 30" opacity="0.85" />
                    <circle cx="200" cy="200" r="142" fill="none" stroke="var(--hud-stroke, #00f0ff)" stroke-width="1.5" stroke-dasharray="6, 8" opacity="0.6" />
                </g>

                <g id="ring-mid-gears" style="transform-origin: 200px 200px; animation: spinCounter var(--spin-mid, 18s) linear infinite;">
                    <circle cx="200" cy="200" r="122" fill="none" stroke="var(--hud-stroke-sec, #38bdf8)" stroke-width="5" stroke-dasharray="20, 10, 10, 10" opacity="0.9" />
                    <circle cx="200" cy="200" r="106" fill="none" stroke="var(--hud-stroke-sec, #38bdf8)" stroke-width="2" stroke-dasharray="4, 6" />
                </g>

                <circle id="wave-reactive-ring" cx="200" cy="200" r="92" fill="none" stroke="var(--hud-stroke, #00f0ff)" stroke-width="2" opacity="0.4" style="transform-origin: 200px 200px;" />

                <g id="ring-inner" style="transform-origin: 200px 200px; animation: spinClockwise var(--spin-inner, 10s) linear infinite;">
                    <circle cx="200" cy="200" r="74" fill="none" stroke="var(--hud-stroke, #00f0ff)" stroke-width="2" stroke-dasharray="18, 8, 30, 8" />
                </g>

                <ellipse cx="200" cy="200" rx="44" ry="16" fill="none" stroke="var(--hud-stroke-sec, #38bdf8)" stroke-width="1" opacity="0.5" />
                <ellipse cx="200" cy="200" rx="16" ry="44" fill="none" stroke="var(--hud-stroke-sec, #38bdf8)" stroke-width="1" opacity="0.5" />

                <circle id="core-glow" cx="200" cy="200" r="48" fill="var(--hud-fill, rgba(0, 240, 255, 0.15))" stroke="var(--hud-stroke, #00f0ff)" stroke-width="2.5" style="transform-origin: 200px 200px;" />
                <circle id="core-center" cx="200" cy="200" r="20" fill="var(--hud-stroke, #00f0ff)" opacity="0.85" style="transform-origin: 200px 200px;" />
            </svg>
        </div>

        <!-- Kybernetische Unterleiste (Einfache Deko-Ringe) -->
        <div style="display: flex; gap: 8px; margin-top: 14px; opacity: 0.65;">
            <svg width="20" height="20" viewBox="0 0 40 40"><circle cx="20" cy="20" r="16" fill="none" stroke="#00f0ff" stroke-width="2" stroke-dasharray="15, 10"/></svg>
            <svg width="20" height="20" viewBox="0 0 40 40"><circle cx="20" cy="20" r="16" fill="none" stroke="#00f0ff" stroke-width="1.5" stroke-dasharray="8, 6"/></svg>
            <svg width="20" height="20" viewBox="0 0 40 40"><circle cx="20" cy="20" r="16" fill="none" stroke="#00f0ff" stroke-width="2" stroke-dasharray="25, 12"/></svg>
            <svg width="20" height="20" viewBox="0 0 40 40"><circle cx="20" cy="20" r="16" fill="none" stroke="#00f0ff" stroke-width="1.5" stroke-dasharray="4, 4"/></svg>
            <svg width="20" height="20" viewBox="0 0 40 40"><circle cx="20" cy="20" r="16" fill="none" stroke="#00f0ff" stroke-width="2" stroke-dasharray="18, 8"/></svg>
            <svg width="20" height="20" viewBox="0 0 40 40"><circle cx="20" cy="20" r="16" fill="none" stroke="#00f0ff" stroke-width="1.5" stroke-dasharray="10, 10"/></svg>
        </div>

    </div>

    <style>
        :root {
            --hud-stroke: #00f0ff;
            --hud-stroke-sec: #38bdf8;
            --hud-fill: rgba(0, 240, 255, 0.15);
            --spin-outer: 32s;
            --spin-mid: 18s;
            --spin-inner: 10s;
        }

        #arc-reactor circle, #arc-reactor g {
            transition: stroke 1.0s cubic-bezier(0.25, 1, 0.5, 1),
                        fill 1.0s cubic-bezier(0.25, 1, 0.5, 1);
        }

        @keyframes spinClockwise { 100% { transform: rotate(360deg); } }
        @keyframes spinCounter { 100% { transform: rotate(-360deg); } }

        @keyframes smoothPulse {
            0%, 100% { transform: scale(1); filter: drop-shadow(0 0 6px var(--hud-stroke)); opacity: 0.8; }
            50% { transform: scale(1.06); filter: drop-shadow(0 0 18px var(--hud-stroke)); opacity: 1; }
        }
    </style>

    <script>
    let isSleep = __IS_SLEEP__;
    let isMuted = false;
    const audioB64 = "__AUDIO_B64__";
    const targetLang = "__TARGET_LANG__";

    const root = document.documentElement;
    const coreGlow = document.getElementById('core-glow');
    const coreCenter = document.getElementById('core-center');
    const waveRing = document.getElementById('wave-reactive-ring');
    const slashLine = document.getElementById('mic-slash-line');
    const svgMic = document.getElementById('svg-mic-icon');

    function applyState(mode) {
        if (mode === 'sleep') {
            // RUHEMODUS: Sehr langsame Rotation & Rote Farbe
            root.style.setProperty('--hud-stroke', '#ef4444');
            root.style.setProperty('--hud-stroke-sec', '#991b1b');
            root.style.setProperty('--hud-fill', 'rgba(239, 68, 68, 0.12)');
            root.style.setProperty('--spin-outer', '70s');
            root.style.setProperty('--spin-mid', '48s');
            root.style.setProperty('--spin-inner', '30s');
            coreGlow.style.animation = 'none';
        } else if (mode === 'processing') {
            // VERARBEITUNG: Extrem schnelle Rotation während des Nachdenkens
            root.style.setProperty('--hud-stroke', '#38bdf8');
            root.style.setProperty('--hud-stroke-sec', '#0284c7');
            root.style.setProperty('--hud-fill', 'rgba(56, 189, 248, 0.25)');
            root.style.setProperty('--spin-outer', '2.5s');
            root.style.setProperty('--spin-mid', '1.5s');
            root.style.setProperty('--spin-inner', '0.8s');
            coreGlow.style.animation = 'smoothPulse 0.4s ease-in-out infinite';
        } else if (mode === 'speaking') {
            // ANTWORT (Jarvis spricht): Normale Rotation + Magenta (Audiowave läuft zusätzlich)
            root.style.setProperty('--hud-stroke', '#c084fc');
            root.style.setProperty('--hud-stroke-sec', '#a855f7');
            root.style.setProperty('--hud-fill', 'rgba(192, 132, 252, 0.2)');
            root.style.setProperty('--spin-outer', '24s');
            root.style.setProperty('--spin-mid', '14s');
            root.style.setProperty('--spin-inner', '8s');
            coreGlow.style.animation = 'none';
        } else if (mode === 'listening') {
            // SPRECHEN (Sir spricht): Pulsierend Gelb
            root.style.setProperty('--hud-stroke', '#facc15');
            root.style.setProperty('--hud-stroke-sec', '#f59e0b');
            root.style.setProperty('--hud-fill', 'rgba(250, 204, 21, 0.2)');
            root.style.setProperty('--spin-outer', '18s');
            root.style.setProperty('--spin-mid', '11s');
            root.style.setProperty('--spin-inner', '6s');
            coreGlow.style.animation = 'smoothPulse 0.8s ease-in-out infinite';
        } else {
            // STANDBY: Normale ruhige Rotation
            root.style.setProperty('--hud-stroke', '#00f0ff');
            root.style.setProperty('--hud-stroke-sec', '#38bdf8');
            root.style.setProperty('--hud-fill', 'rgba(0, 240, 255, 0.15)');
            root.style.setProperty('--spin-outer', '32s');
            root.style.setProperty('--spin-mid', '18s');
            root.style.setProperty('--spin-inner', '10s');
            coreGlow.style.animation = 'smoothPulse 2.8s ease-in-out infinite';
        }
    }

    function updateMicUI() {
        if (isMuted) {
            slashLine.style.display = 'block';
            svgMic.style.stroke = '#ef4444';
            applyState('standby');
        } else {
            slashLine.style.display = 'none';
            svgMic.style.stroke = '#00f0ff';
            applyState(isSleep ? 'sleep' : 'standby');
        }
    }

    window.toggleHudMic = function() {
        isMuted = !isMuted;
        updateMicUI();
        if (!isMuted && rec) {
            try { rec.start(); } catch(e) {}
        }
    };

    if (isSleep) applyState('sleep');
    else applyState('standby');

    // --- Web Audio API Waveform ---
    let audioCtx = null;
    let animFrame = null;

    if (audioB64.length > 0) {
        applyState('speaking');
        try {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            if (audioCtx.state === 'suspended') audioCtx.resume();

            const audio = new Audio("data:audio/mp3;base64," + audioB64);
            const source = audioCtx.createMediaElementSource(audio);
            const analyser = audioCtx.createAnalyser();
            analyser.fftSize = 64;
            source.connect(analyser);
            analyser.connect(audioCtx.destination);

            const dataArray = new Uint8Array(analyser.frequencyBinCount);

            function renderWave() {
                analyser.getByteFrequencyData(dataArray);
                let sum = 0;
                for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
                let norm = Math.min((sum / dataArray.length) / 120, 1.8);

                if (coreGlow) {
                    coreGlow.setAttribute('r', 48 + (norm * 14));
                    coreGlow.style.filter = 'drop-shadow(0 0 ' + (10 + norm * 24) + 'px #c084fc)';
                }
                if (waveRing) {
                    waveRing.setAttribute('r', 92 + (norm * 22));
                    waveRing.setAttribute('stroke-width', 2 + (norm * 4));
                    waveRing.style.opacity = 0.35 + (norm * 0.65);
                }
                if (coreCenter) {
                    coreCenter.setAttribute('r', 20 + (norm * 7));
                }

                animFrame = requestAnimationFrame(renderWave);
            }

            audio.play().then(() => {
                renderWave();
            }).catch(() => {
                finishSpeaking();
            });

            audio.onended = () => {
                finishSpeaking();
            };

            function finishSpeaking() {
                if (animFrame) cancelAnimationFrame(animFrame);
                if (coreGlow) {
                    coreGlow.setAttribute('r', 48);
                    coreGlow.style.filter = 'drop-shadow(0 0 10px var(--hud-stroke))';
                }
                if (waveRing) {
                    waveRing.setAttribute('r', 92);
                    waveRing.setAttribute('stroke-width', 2);
                    waveRing.style.opacity = '0.4';
                }
                if (isSleep) {
                    applyState('sleep');
                } else {
                    startFollowUp();
                }
            }
        } catch(e) {
            applyState(isSleep ? 'sleep' : 'standby');
        }
    }

    // --- Follow-Up Zuhören nach der Antwort (7 Sekunden) ---
    let followUpTimer = null;
    function startFollowUp() {
        if (isSleep || isMuted) {
            applyState('standby');
            return;
        }
        isListeningCommand = true;
        applyState('listening');

        if (rec) {
            try { rec.start(); } catch(e) {}
        }

        clearTimeout(followUpTimer);
        followUpTimer = setTimeout(() => {
            if (isListeningCommand && fullCommand.trim().length === 0) {
                isListeningCommand = false;
                applyState('standby');
            }
        }, 7000);
    }

    // --- Spracherkennung (VOLLKOMMEN TEXT-FREI) ---
    let rec = null;
    let isListeningCommand = false;
    let silenceTimeout = null;
    let fullCommand = "";

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
        rec = new SpeechRecognition();
        rec.continuous = true;
        rec.interimResults = true;
        rec.lang = targetLang;

        if (audioB64.length === 0) {
            try { rec.start(); } catch(e) {}
        }

        rec.onresult = (event) => {
            if (isMuted) return;

            let interim = "";
            let final = "";
            for (let i = event.resultIndex; i < event.results.length; ++i) {
                if (event.results[i].isFinal) final += event.results[i][0].transcript;
                else interim += event.results[i][0].transcript;
            }

            let raw = (final || interim).trim();
            let lower = raw.toLowerCase();

            // Ruhemodus Wake-Up
            const wakeWords = ["aufwachen", "wach auf", "wake up"];
            if (isSleep) {
                if (wakeWords.some(w => lower.includes(w))) {
                    isSleep = false;
                    applyState('processing'); // Rotiert sofort blitzschnell
                    sendTextCommand("Hey Jarvis aufwachen");
                }
                return;
            }

            // Normalmodus Wake-Word
            if (!isListeningCommand && (lower.includes("hey jarvis") || lower.includes("jarvis"))) {
                isListeningCommand = true;
                applyState('listening');
                raw = raw.replace(/hey jarvis/gi, "").replace(/jarvis/gi, "").trim();
            }

            if (isListeningCommand) {
                clearTimeout(followUpTimer);
                let cleanCmd = raw.replace(/^hey jarvis/gi, "").replace(/^jarvis/gi, "").trim();
                if (cleanCmd.length > 0) {
                    fullCommand = cleanCmd;

                    clearTimeout(silenceTimeout);
                    silenceTimeout = setTimeout(() => {
                        if (fullCommand.trim().length > 0) {
                            applyState('processing'); // Die Ringe fangen extrem schnell an zu drehen!
                            sendTextCommand(fullCommand);
                            fullCommand = "";
                            isListeningCommand = false;
                        }
                    }, 1000);
                }
            }
        };

        rec.onend = () => {
            if (!isMuted && !isSleep) {
                try { rec.start(); } catch(e) {}
            }
        };
    }

    // Übergabe des akustischen Befehls in das verborgene Streamlit-Eingabefeld
    function sendTextCommand(cmd) {
        const parentDoc = window.parent.document;
        const ta = parentDoc.querySelector('textarea[data-testid="stChatInputTextArea"]');
        if (ta) {
            const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
            setter.call(ta, "[VOICE] " + cmd);
            ta.dispatchEvent(new Event('input', { bubbles: true }));

            setTimeout(() => {
                const btn = parentDoc.querySelector('button[data-testid="stChatInputSubmitButton"]');
                if (btn) btn.click();
                else {
                    ta.dispatchEvent(new KeyboardEvent('keydown', {
                        bubbles: true, cancelable: true, keyCode: 13, key: 'Enter'
                    }));
                }
            }, 100);
        }
    }

    // Ermöglicht direktes Sprechen durch Klick in die Mitte
    window.triggerListenDirectly = function() {
        if (isSleep) {
            isSleep = false;
            applyState('processing');
            sendTextCommand("Hey Jarvis aufwachen");
            return;
        }
        isListeningCommand = true;
        applyState('listening');
        if (rec) {
            try { rec.start(); } catch(e) {}
        }
    };
    </script>
    """

    hud_html = (
        hud_template.replace("__IS_SLEEP__", str(is_sleep).lower())
        .replace("__AUDIO_B64__", audio_payload)
        .replace("__TARGET_LANG__", rec_lang_code)
    )

    components.html(hud_html, height=440)


# === RECHTE SPALTE: HARDWARE- & TELEMETRIE-STATUS ===
with col_right:
    st.markdown("""
    <div class="hud-card">
        <div class="hud-header"><span>⚡ TELEMETRIE // KERN</span> <span>[OK]</span></div>
        <div style="display: flex; justify-content: space-between; font-size: 11px; margin-top: 4px;">
            <span>KERN-INTEGRITÄT</span> <span style="color:#00f0ff;">99.4%</span>
        </div>
        <div style="background: rgba(0,240,255,0.1); height: 5px; border-radius: 2px; overflow: hidden; margin-top: 2px;">
            <div style="background: #00f0ff; width: 99%; height: 100%;"></div>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 11px; margin-top: 8px;">
            <span>LPU VERARBEITUNG</span> <span style="color:#38bdf8;">0.18s</span>
        </div>
        <div style="background: rgba(0,240,255,0.1); height: 5px; border-radius: 2px; overflow: hidden; margin-top: 2px;">
            <div style="background: #38bdf8; width: 88%; height: 100%;"></div>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 11px; margin-top: 8px;">
            <span>AUDIO STREAM</span> <span style="color:#10b981;">SYNCHRON</span>
        </div>
        <div style="background: rgba(0,240,255,0.1); height: 5px; border-radius: 2px; overflow: hidden; margin-top: 2px;">
            <div style="background: #10b981; width: 100%; height: 100%;"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# Globale Befehlseingabe (Für Tastatureingaben)
chat_text = st.chat_input("Befehl an J.A.R.V.I.S., Sir...")
if chat_text:
    if chat_text.startswith("[VOICE]"):
        clean = chat_text.replace("[VOICE]", "").strip()
        process_query(clean, is_voice=True)
    else:
        process_query(chat_text, is_voice=False)
    st.rerun()
