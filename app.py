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

# Wide-Layout für volles HUD-Erlebnis
st.set_page_config(page_title="J.A.R.V.I.S. HUD", page_icon="🤖", layout="wide")

# --- Futuristic Cyberpunk / Iron Man HUD CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;800;900&family=Rajdhani:wght@500;600;700&display=swap');

    /* Global Dark Grid Background */
    .stApp {
        background-color: #030712;
        background-image: 
            linear-gradient(rgba(0, 240, 255, 0.04) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0, 240, 255, 0.04) 1px, transparent 1px);
        background-size: 35px 35px;
        color: #cffafe;
        font-family: 'Rajdhani', sans-serif;
    }

    /* Sci-Fi HUD Box */
    .hud-box {
        background: rgba(4, 18, 32, 0.75);
        border: 1px solid #00f0ff66;
        box-shadow: 0 0 15px rgba(0, 240, 255, 0.12) inset, 0 0 10px rgba(0, 240, 255, 0.08);
        border-radius: 4px;
        clip-path: polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 12px 100%, 0 calc(100% - 12px));
        padding: 14px 18px;
        margin-bottom: 15px;
        backdrop-filter: blur(6px);
    }

    .hud-title {
        font-family: 'Orbitron', monospace;
        font-size: 11px;
        letter-spacing: 2px;
        color: #38bdf8;
        text-transform: uppercase;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        gap: 6px;
        border-bottom: 1px solid rgba(56, 189, 248, 0.25);
        padding-bottom: 4px;
    }

    .hud-value {
        font-family: 'Orbitron', monospace;
        font-size: 22px;
        font-weight: 700;
        color: #00f0ff;
        text-shadow: 0 0 10px rgba(0, 240, 255, 0.6);
    }

    .hud-sub {
        font-size: 13px;
        color: #94a3b8;
    }

    /* Telemetrie-Balken wie in der Vorlage */
    .telemetry-bar {
        background: rgba(0, 240, 255, 0.1);
        border: 1px solid #00f0ff55;
        border-radius: 2px;
        height: 12px;
        overflow: hidden;
        margin-top: 6px;
    }
    .telemetry-fill {
        background: linear-gradient(90deg, #00f0ff, #38bdf8);
        height: 100%;
        box-shadow: 0 0 8px #00f0ff;
    }

    /* Expander / Drawer Styling */
    .streamlit-expanderHeader {
        background: rgba(4, 18, 32, 0.85) !important;
        border: 1px solid #00f0ff55 !important;
        color: #38bdf8 !important;
        font-family: 'Orbitron', monospace !important;
        font-size: 12px !important;
    }
    
    /* Input Styling */
    .stChatInputContainer {
        border-color: #00f0ff55 !important;
        box-shadow: 0 0 12px rgba(0, 240, 255, 0.2) !important;
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
        st.error(f"Konnte Modelle nicht laden: {e}")
        return []

available_models = get_available_models()

def build_system_prompt():
    memories = get_all_memories()
    mem_text = "\n".join([f"- {k}: {v}" for k, v in memories.items()]) if memories else "Keine Einträge vorhanden."
    
    return f"""Du bist J.A.R.V.I.S., die hochentwickelte KI von Sir.
1. Sprich den Nutzer stets diskret und loyal mit 'Sir' an.
2. SPRACHE: Antworte IMMER exakt in der Sprache, in der Sir dich anspricht (Deutsch -> Deutsch, Englisch -> Englisch).
3. Sei präzise, loyal, trocken-humorvoll und halte dich extrem kurz (1-2 Sätze).
4. Gib niemals interne Denkprozesse oder Meta-Kommentare aus.
5. Wenn Sir dir befiehlt schlafen zu gehen, leise zu sein oder den Ruhemodus zu aktivieren, rufe SOFORT 'run_protocol' mit protocol_name='ruhemodus' auf.
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

# --- Linke Seitenleiste: Audio, Sensoren & Systemsteuerung ---
with st.sidebar:
    st.markdown("<h3 style='font-family: Orbitron; color: #00f0ff;'>⚙️ SYSTEM CONTROL</h3>", unsafe_allow_html=True)
    
    if st.session_state.sleep_mode:
        st.warning("🌙 RUHEMODUS AKTIV")
        if st.button("⚡ REAKTIVIEREN (WAKE UP)"):
            st.session_state.sleep_mode = False
            st.rerun()
        enable_wakeword = False
        enable_tts = False
    else:
        enable_wakeword = st.toggle("🎤 'Hey Jarvis' lauschen", value=False)
        enable_tts = st.toggle("🔊 Sprachausgabe erlauben", value=False)

    input_lang = st.selectbox("Mikrofon-Sprache:", ["Deutsch (de-DE)", "English (en-US)"])
    rec_lang_code = "de-DE" if "Deutsch" in input_lang else "en-US"

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
    if any(c in lower for c in "äöüß"):
        return "de"
    german_markers = {"der", "die", "das", "und", "ist", "nicht", "ich", "wir", "habe", "uhr", "termin", "gerne"}
    english_markers = {"the", "and", "is", "not", "have", "you", "will", "sir", "all", "ready", "scheduled"}
    words = set(lower.split())
    return "en" if len(words & english_markers) > len(words & german_markers) else "de"

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
    if st.session_state.sleep_mode:
        if any(w in user_text.lower() for w in ["aufwachen", "wake up", "hallo", "guten morgen", "online"]):
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
            clean_tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]

            st.session_state.messages.append({
                "role": "assistant",
                "content": response_message.content or "",
                "tool_calls": clean_tool_calls,
            })

            for tool_call in tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                function_output = TOOL_MAP.get(func_name, lambda **x: "Funktion nicht verfügbar")(**func_args)

                if "TRIGGER_SLEEP_MODE" in str(function_output):
                    triggered_sleep = True

                st.session_state.messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": func_name,
                    "content": str(function_output),
                })

            second_params = {"model": MODEL_NAME, "messages": st.session_state.messages}
            if "gpt-oss" in MODEL_NAME:
                second_params["extra_body"] = {"include_reasoning": False}

            second_response = client.chat.completions.create(**second_params)
            reply = second_response.choices[0].message.content
        else:
            reply = response_message.content

        if reply and "</think>" in reply:
            reply = reply.split("</think>")[-1].strip()
        if reply and "Thus final." in reply:
            reply = reply.split("Thus final.")[-1].strip()

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

# --- HUD LAYOUT IN 3 SPALTEN ---
now = datetime.now(ZoneInfo("Europe/Berlin"))
col_left, col_center, col_right = st.columns([3.2, 5.6, 3.2])

# === LINKE SPALTE: DATEN & SENSOREN ===
with col_left:
    # Kachel 1: Zeit & Datum
    st.markdown(f"""
    <div class="hud-box">
        <div class="hud-title">⏱️ CHRONO // SYSTEMZEIT</div>
        <div class="hud-value">{now.strftime('%H:%M:%S')} <span style="font-size: 14px;">CET</span></div>
        <div class="hud-sub">{now.strftime('%A, %d.%m.%Y')}</div>
    </div>
    """, unsafe_allow_html=True)

    # Kachel 2: Google Kalender Status
    cal_preview = list_calendar_events(days_ahead=3)
    first_lines = "\n".join(cal_preview.split("\n")[:4]) if isinstance(cal_preview, str) else "Keine Daten"
    st.markdown(f"""
    <div class="hud-box">
        <div class="hud-title">📅 KALENDER // AGENDA</div>
        <div style="font-size: 13px; line-height: 1.5; color: #7dd3fc; white-space: pre-line;">{first_lines}</div>
    </div>
    """, unsafe_allow_html=True)

    # Kachel 3: Langzeitgedächtnis
    mems = get_all_memories()
    mem_items = "".join([f"<div style='margin-bottom: 4px;'>• <b style='color:#38bdf8;'>{k}:</b> {v}</div>" for k, v in list(mems.items())[:3]]) or "<i>Keine Einträge hinterlegt</i>"
    st.markdown(f"""
    <div class="hud-box">
        <div class="hud-title">🧠 LANGZEITGEDÄCHTNIS</div>
        <div style="font-size: 12px; color: #bae6fd;">{mem_items}</div>
    </div>
    """, unsafe_allow_html=True)


# === MITTLERE SPALTE: DAS PULSIERENDE ARC-REACTOR-HOLOGRAMM ===
with col_center:
    audio_payload = st.session_state.latest_audio_b64
    st.session_state.latest_audio_b64 = ""
    is_sleep = st.session_state.sleep_mode

    hud_html = f"""
    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; width: 100%;">
        
        <!-- Animated Holographic Arc Reactor (Centerpiece) -->
        <div id="reactor-wrapper" style="position: relative; width: 340px; height: 340px; display: flex; align-items: center; justify-content: center;">
            <svg id="arc-reactor" viewBox="0 0 400 400" width="340" height="340" style="transition: all 0.5s ease;">
                
                <!-- Background Glow Core -->
                <circle cx="200" cy="200" r="180" fill="none" stroke="rgba(0, 240, 255, 0.08)" stroke-width="1" />
                <circle cx="200" cy="200" r="160" fill="none" stroke="rgba(0, 240, 255, 0.15)" stroke-dasharray="6, 8" />

                <!-- Outer Segmented Rotating Ring -->
                <g id="ring-outer" style="transform-origin: 200px 200px; animation: spinClockwise 22s linear infinite;">
                    <circle cx="200" cy="200" r="145" fill="none" stroke="var(--hud-primary, #00f0ff)" stroke-width="3" stroke-dasharray="90, 20, 40, 20" opacity="0.8" />
                    <circle cx="200" cy="200" r="135" fill="none" stroke="var(--hud-primary, #00f0ff)" stroke-width="1" stroke-dasharray="10, 10" opacity="0.6" />
                </g>

                <!-- Middle Reverse Rotating Segment Ring -->
                <g id="ring-mid" style="transform-origin: 200px 200px; animation: spinCounter 14s linear infinite;">
                    <circle cx="200" cy="200" r="115" fill="none" stroke="var(--hud-secondary, #38bdf8)" stroke-width="4" stroke-dasharray="35, 12, 15, 12" opacity="0.9" />
                    <circle cx="200" cy="200" r="100" fill="none" stroke="var(--hud-secondary, #38bdf8)" stroke-width="1.5" stroke-dasharray="4, 6" />
                </g>

                <!-- Inner Precision Ring -->
                <g id="ring-inner" style="transform-origin: 200px 200px; animation: spinClockwise 8s linear infinite;">
                    <circle cx="200" cy="200" r="75" fill="none" stroke="var(--hud-primary, #00f0ff)" stroke-width="2" stroke-dasharray="20, 8, 40, 8" />
                </g>

                <!-- Core Pulsing Sphere -->
                <circle id="core-glow" cx="200" cy="200" r="50" fill="rgba(0, 240, 255, 0.12)" stroke="var(--hud-primary, #00f0ff)" stroke-width="2.5" style="transform-origin: 200px 200px; animation: corePulse 2s ease-in-out infinite;" />
                <circle id="core-center" cx="200" cy="200" r="22" fill="var(--hud-primary, #00f0ff)" opacity="0.85" />
            </svg>

            <!-- Status HUD Overlay Text in Center -->
            <div style="position: absolute; text-align: center; pointer-events: none;">
                <div id="hud-status-badge" style="
                    font-family: 'Orbitron', monospace;
                    font-size: 11px;
                    letter-spacing: 2px;
                    color: #fff;
                    background: rgba(3, 15, 29, 0.85);
                    padding: 4px 10px;
                    border: 1px solid #00f0ff55;
                    border-radius: 4px;
                    text-transform: uppercase;
                ">STANDBY</div>
            </div>
        </div>

        <!-- Real-time Voice Detection Bar -->
        <div style="margin-top: 10px; text-align: center; width: 100%;">
            <span id="hud-substatus" style="font-family: 'Rajdhani', sans-serif; font-size: 14px; color: #7dd3fc; letter-spacing: 1px;">Sensoren bereit</span>
            <div id="hud-voice-text" style="font-family: 'Orbitron', monospace; font-size: 13px; color: #38bdf8; min-height: 20px; margin-top: 4px;"></div>
        </div>

    </div>

    <style>
        :root {
            --hud-primary: #00f0ff;
            --hud-secondary: #38bdf8;
        }

        @keyframes spinClockwise {
            100% { transform: rotate(360deg); }
        }
        @keyframes spinCounter {
            100% { transform: rotate(-360deg); }
        }
        @keyframes corePulse {
            0%, 100% { transform: scale(1); opacity: 0.7; }
            50% { transform: scale(1.1); opacity: 1; filter: drop-shadow(0 0 14px var(--hud-primary)); }
        }
        @keyframes speakingFrenzy {
            0%, 100% { transform: scale(1); filter: drop-shadow(0 0 8px #a855f7); }
            50% { transform: scale(1.18); filter: drop-shadow(0 0 25px #c084fc); }
        }
    </style>

    <script>
    const isSleep = {str(is_sleep).lower()};
    const active = {str(enable_wakeword).lower()} && !isSleep;
    const audioB64 = "{audio_payload}";
    const targetLang = "{rec_lang_code}";

    const root = document.documentElement;
    const badge = document.getElementById('hud-status-badge');
    const substatus = document.getElementById('hud-substatus');
    const voiceText = document.getElementById('hud-voice-text');
    const core = document.getElementById('core-glow');

    function applyState(mode) {
        if (mode === 'sleep') {
            root.style.setProperty('--hud-primary', '#ef4444');
            root.style.setProperty('--hud-secondary', '#991b1b');
            badge.innerText = 'OFFLINE';
            badge.style.borderColor = '#ef4444';
            substatus.innerText = '🌙 Ruhemodus aktiv – Sensoren verriegelt';
        } else if (mode === 'speaking') {
            root.style.setProperty('--hud-primary', '#c084fc');
            root.style.setProperty('--hud-secondary', '#a855f7');
            badge.innerText = 'JARVIS SPRICHT';
            badge.style.borderColor = '#c084fc';
            substatus.innerText = 'Übertrage akustische Antwort...';
            core.style.animation = 'speakingFrenzy 0.6s ease-in-out infinite';
        } else if (mode === 'listening') {
            root.style.setProperty('--hud-primary', '#facc15');
            root.style.setProperty('--hud-secondary', '#38bdf8');
            badge.innerText = 'ERKENNUNG';
            badge.style.borderColor = '#facc15';
            substatus.innerText = 'Sir spricht – Akustik-Prozessor aktiv...';
            core.style.animation = 'corePulse 0.8s ease-in-out infinite';
        } else {
            root.style.setProperty('--hud-primary', '#00f0ff');
            root.style.setProperty('--hud-secondary', '#38bdf8');
            badge.innerText = active ? 'ONLINE' : 'STANDBY';
            badge.style.borderColor = '#00f0ff55';
            substatus.innerText = active ? 'Warte auf "Hey Jarvis"...' : 'Mikrofon inaktiv';
            core.style.animation = 'corePulse 2.5s ease-in-out infinite';
        }
    }

    if (isSleep) {
        applyState('sleep');
    } else {
        applyState('standby');
    }

    // --- Audioausgabe & Farbumschaltung ---
    let isSpeaking = false;
    if (audioB64.length > 0) {
        isSpeaking = true;
        applyState('speaking');
        const audio = new Audio("data:audio/mp3;base64," + audioB64);
        audio.play().catch(() => {
            isSpeaking = false;
            applyState(isSleep ? 'sleep' : 'standby');
        });
        audio.onended = () => {
            isSpeaking = false;
            applyState(isSleep ? 'sleep' : 'standby');
            if (active && !isSleep) {
                try { rec.start(); } catch(e) {}
            }
        };
    }

    // --- Spracherkennung & Interaktiver Puls ---
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
        const rec = new SpeechRecognition();
        rec.continuous = true;
        rec.interimResults = true;
        rec.lang = targetLang;

        let isListeningCommand = false;
        let silenceTimeout = null;
        let fullCommand = "";

        if (active && !isSpeaking && !isSleep) {
            try { rec.start(); } catch(e) {}
        }

        rec.onresult = (event) => {
            if (isSpeaking || isSleep) return;

            let interim = "";
            let final = "";
            for (let i = event.resultIndex; i < event.results.length; ++i) {
                if (event.results[i].isFinal) final += event.results[i][0].transcript;
                else interim += event.results[i][0].transcript;
            }

            let raw = (final || interim).trim();
            let lower = raw.toLowerCase();

            if (!isListeningCommand && (lower.includes("hey jarvis") || lower.includes("jarvis"))) {
                isListeningCommand = true;
                applyState('listening');
                raw = raw.replace(/hey jarvis/gi, "").replace(/jarvis/gi, "").trim();
            }

            if (isListeningCommand) {
                let cleanCmd = raw.replace(/^hey jarvis/gi, "").replace(/^jarvis/gi, "").trim();
                if (cleanCmd.length > 0) {
                    fullCommand = cleanCmd;
                    voiceText.innerText = '"' + fullCommand + '"';

                    clearTimeout(silenceTimeout);
                    silenceTimeout = setTimeout(() => {
                        if (fullCommand.trim().length > 0) {
                            const parentDoc = window.parent.document;
                            const ta = parentDoc.querySelector('textarea[data-testid="stChatInputTextArea"]');
                            if (ta) {
                                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                                nativeSetter.call(ta, "[VOICE] " + fullCommand);
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
                            fullCommand = "";
                            isListeningCommand = false;
                            applyState('standby');
                        }
                    }, 1100);
                }
            }
        };

        rec.onend = () => {
            if (active && !isSpeaking && !isSleep) {
                try { rec.start(); } catch(e) {}
            }
        };
    }
    </script>
    """
    components.html(hud_html, height=430)


# === RECHTE SPALTE: TELEMETRIE & AUSKLAPPBARER CHAT ===
with col_right:
    # Kachel 4: Systemdiagnose (wie die Balken im oberen Bildbereich)
    st.markdown(f"""
    <div class="hud-box">
        <div class="hud-title">⚡ SYSTEM STATUS // HARDWARE</div>
        <div style="display: flex; justify-content: space-between; font-size: 11px; margin-top: 4px;">
            <span>KERN-INTEGRITÄT</span> <span>98%</span>
        </div>
        <div class="telemetry-bar"><div class="telemetry-fill" style="width: 98%;"></div></div>
        
        <div style="display: flex; justify-content: space-between; font-size: 11px; margin-top: 8px;">
            <span>LPU LATENZ (GROQ)</span> <span>20%</span>
        </div>
        <div class="telemetry-bar"><div class="telemetry-fill" style="width: 20%;"></div></div>

        <div style="display: flex; justify-content: space-between; font-size: 11px; margin-top: 8px;">
            <span>SYNAPSEN-INDEX</span> <span>50%</span>
        </div>
        <div class="telemetry-bar"><div class="telemetry-fill" style="width: 50%;"></div></div>
    </div>
    """, unsafe_allow_html=True)

    # Kachel 5: Das ausklappbare Chat-Fenster
    with st.expander("🗨️ KOMMUNIKATIONS-PROTOKOLL", expanded=True):
        chat_container = st.container(height=260)
        with chat_container:
            for msg in st.session_state.messages[1:]:
                role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
                content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
                if role in ["user", "assistant"] and content:
                    with st.chat_message(role):
                        st.write(content)

# --- Chat-Eingabe ganz unten ---
chat_text = st.chat_input("Befehl an J.A.R.V.I.S. übermitteln, Sir...")
if chat_text:
    if chat_text.startswith("[VOICE]"):
        clean_text = chat_text.replace("[VOICE]", "").strip()
        process_query(clean_text, is_voice=True)
    else:
        process_query(chat_text, is_voice=False)
    st.rerun()
