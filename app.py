import os
import json
import asyncio
import base64
import streamlit as st
import streamlit.components.v1 as components
from groq import Groq
import edge_tts
from gradio_client import Client
from jarvis_tools import TOOLS_SCHEMA, TOOL_MAP, get_all_memories

st.set_page_config(page_title="J.A.R.V.I.S.", page_icon="🤖", layout="centered")
st.title("J.A.R.V.I.S.")
st.caption("Systemstatus: Online. Bereit für Ihre Anweisungen, Sir.")

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
2. SPRACHE: Antworte IMMER exakt in der Sprache, in der Sir dich anspricht. Spricht Sir Englisch, antworte auf Englisch. Spricht Sir Deutsch, antworte auf Deutsch.
3. Sei präzise, loyal, trocken-humorvoll und halte dich extrem kurz (1-2 Sätze).
4. Wenn Sir dir befiehlt schlafen zu gehen, leise zu sein oder den Ruhemodus zu aktivieren, rufe SOFORT 'run_protocol' mit protocol_name='ruhemodus' auf.
5. Wenn Sir dir Fakten über sich mitteilt, rufe sofort 'save_memory' auf.

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

# Seitenleiste
with st.sidebar:
    st.header("Audio & Sensoren")
    
    if st.session_state.sleep_mode:
        st.warning("🌙 Ruhemodus aktiv")
        if st.button("🔔 Jarvis aufwecken"):
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
    st.header("Langzeitgedächtnis")
    current_memories = get_all_memories()
    if current_memories:
        for k, v in current_memories.items():
            st.text(f"• {k}: {v}")
    else:
        st.caption("Noch keine Fakten gelernt.")

    st.divider()
    if available_models:
        default_idx = available_models.index("openai/gpt-oss-120b") if "openai/gpt-oss-120b" in available_models else 0
        MODEL_NAME = st.selectbox("Aktives Modell:", available_models, index=default_idx)
    else:
        st.error("Keine Modelle gefunden.")
        st.stop()

    if st.button("Chat-Verlauf löschen"):
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
    de_score = len(words & german_markers)
    en_score = len(words & english_markers)
    return "en" if en_score > de_score else "de"

async def generate_edge_voice(text: str, voice_name: str, rate: str = "-3%", pitch: str = "-4Hz") -> bytes:
    communicate = edge_tts.Communicate(text=text, voice=voice_name, rate=rate, pitch=pitch)
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    return audio_data

def generate_voice_audio(text: str) -> bytes:
    """Nutzt MeloTTS für flüssiges Deutsch und Kokoro-82M für Englisch mit Edge-TTS als Fallback."""
    lang = detect_language(text)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    hf_token = st.secrets.get("HF_TOKEN")

    if lang == "de":
        # 1. Deutsches neuronales Modell via MeloTTS
        if hf_token:
            try:
                melo_client = Client("myshell-ai/MeloTTS", hf_token=hf_token)
                result = melo_client.predict(
                    text=text,
                    language="DE",
                    speaker="DE-Default",
                    speed=0.95,
                    api_name="/synthesize"
                )
                with open(result, "rb") as f:
                    return f.read()
            except Exception:
                pass
        # Fallback auf klares, sonores Edge-TTS
        return loop.run_until_complete(generate_edge_voice(text, "de-DE-KillianNeural"))

    else:
        # 2. Englisches Original via Kokoro-82M
        if hf_token:
            try:
                hf_client = Client("hexgrad/Kokoro-82M", hf_token=hf_token)
                result = hf_client.predict(text=text, voice="bm_george")
                with open(result, "rb") as f:
                    return f.read()
            except Exception:
                pass
        # Fallback auf britisches Edge-TTS
        return loop.run_until_complete(generate_edge_voice(text, "en-GB-RyanNeural"))

def process_query(user_text, is_voice=False):
    if st.session_state.sleep_mode:
        if any(w in user_text.lower() for w in ["aufwachen", "wake up", "hallo", "guten morgen", "online"]):
            st.session_state.sleep_mode = False

    st.session_state.messages[0] = {"role": "system", "content": build_system_prompt()}
    st.session_state.messages.append({"role": "user", "content": user_text})

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=st.session_state.messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto",
            temperature=0.5,
        )

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

                if func_name in TOOL_MAP:
                    function_output = TOOL_MAP[func_name](**func_args)
                else:
                    function_output = "Funktion nicht verfügbar."

                if "TRIGGER_SLEEP_MODE" in str(function_output):
                    triggered_sleep = True

                st.session_state.messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": func_name,
                    "content": str(function_output),
                })

            second_response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=st.session_state.messages,
            )
            reply = second_response.choices[0].message.content
        else:
            reply = response_message.content

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
        st.error(f"Fehler bei Groq-Anfrage ({MODEL_NAME}): {e}")

chat_text = st.chat_input("Befehl eingeben, Sir...")

if chat_text:
    if chat_text.startswith("[VOICE]"):
        clean_text = chat_text.replace("[VOICE]", "").strip()
        process_query(clean_text, is_voice=True)
    else:
        process_query(chat_text, is_voice=False)

audio_payload = st.session_state.latest_audio_b64
st.session_state.latest_audio_b64 = ""
is_sleep = st.session_state.sleep_mode

hud_html = f"""
<div id="jarvis-hud" style="
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    margin-bottom: 12px;
    border-radius: 8px;
    background: #0f172a;
    border: 1px solid #1e293b;
    color: #e2e8f0;
    font-family: monospace;
    font-size: 13px;
">
    <div id="hud-dot" style="
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background-color: {'#ef4444' if is_sleep else ('#10b981' if enable_wakeword else '#64748b')};
        box-shadow: 0 0 8px {'#ef4444' if is_sleep else ('#10b981' if enable_wakeword else 'transparent')};
    "></div>
    <span id="hud-status">{'🌙 Ruhemodus aktiv – Alle Sensoren offline' if is_sleep else ('Warte auf "Hey Jarvis"...' if enable_wakeword else 'Mikrofon inaktiv')}</span>
    <span id="hud-text" style="margin-left: auto; color: #38bdf8;"></span>
</div>

<script>
const isSleep = {str(is_sleep).lower()};
const active = {str(enable_wakeword).lower()} && !isSleep;
const audioB64 = "{audio_payload}";
const targetLang = "{rec_lang_code}";
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

if (SpeechRecognition) {{
    const rec = new SpeechRecognition();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = targetLang;

    const dot = document.getElementById('hud-dot');
    const status = document.getElementById('hud-status');
    const hudText = document.getElementById('hud-text');

    let isListeningCommand = false;
    let isSpeaking = false;
    let silenceTimeout = null;
    let followUpTimer = null;
    let fullCommand = "";

    function setStandby() {{
        isListeningCommand = false;
        dot.style.backgroundColor = '#10b981';
        dot.style.boxShadow = '0 0 8px #10b981';
        status.innerText = 'Warte auf "Hey Jarvis"...';
        hudText.innerText = "";
    }}

    function startFollowUp() {{
        if (isSleep) return;
        isListeningCommand = true;
        dot.style.backgroundColor = '#38bdf8';
        dot.style.boxShadow = '0 0 12px #38bdf8';
        status.innerText = "Im Gespräch: Höre zu (ohne Wake-Word)...";

        clearTimeout(followUpTimer);
        followUpTimer = setTimeout(() => {{
            if (isListeningCommand && fullCommand.trim().length === 0) {{
                setStandby();
            }}
        }}, 7000);
    }}

    if (audioB64.length > 0) {{
        isSpeaking = true;
        dot.style.backgroundColor = '#a855f7';
        dot.style.boxShadow = '0 0 10px #a855f7';
        status.innerText = "Jarvis spricht...";

        const audio = new Audio("data:audio/mp3;base64," + audioB64);
        audio.play().catch(() => {{
            isSpeaking = false;
            if (!isSleep) startFollowUp();
        }});

        audio.onended = () => {{
            isSpeaking = false;
            if (isSleep) {{
                dot.style.backgroundColor = '#ef4444';
                dot.style.boxShadow = '0 0 8px #ef4444';
                status.innerText = '🌙 Ruhemodus aktiv – Alle Sensoren offline';
                try {{ rec.stop(); }} catch(e) {{}}
            }} else {{
                try {{ rec.start(); }} catch(e) {{}}
                startFollowUp();
            }}
        }};
    }} else if (active) {{
        try {{ rec.start(); }} catch(e) {{}}
    }}

    rec.onresult = (event) => {{
        if (isSpeaking || isSleep) return;

        let interim = "";
        let final = "";

        for (let i = event.resultIndex; i < event.results.length; ++i) {{
            if (event.results[i].isFinal) final += event.results[i][0].transcript;
            else interim += event.results[i][0].transcript;
        }}

        let raw = (final || interim).trim();
        let lower = raw.toLowerCase();

        if (!isListeningCommand && (lower.includes("hey jarvis") || lower.includes("jarvis"))) {{
            isListeningCommand = true;
            dot.style.backgroundColor = '#38bdf8';
            dot.style.boxShadow = '0 0 12px #38bdf8';
            status.innerText = "Höre zu, Sir...";
            raw = raw.replace(/hey jarvis/gi, "").replace(/jarvis/gi, "").trim();
        }}

        if (isListeningCommand) {{
            clearTimeout(followUpTimer);
            let cleanCmd = raw.replace(/^hey jarvis/gi, "").replace(/^jarvis/gi, "").trim();

            if (cleanCmd.length > 0) {{
                fullCommand = cleanCmd;
                hudText.innerText = '"' + fullCommand + '"';

                clearTimeout(silenceTimeout);
                silenceTimeout = setTimeout(() => {{
                    if (fullCommand.trim().length > 0) {{
                        const parentDoc = window.parent.document;
                        const ta = parentDoc.querySelector('textarea[data-testid="stChatInputTextArea"]');
                        if (ta) {{
                            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                            nativeSetter.call(ta, "[VOICE] " + fullCommand);
                            ta.dispatchEvent(new Event('input', {{ bubbles: true }}));

                            setTimeout(() => {{
                                const btn = parentDoc.querySelector('button[data-testid="stChatInputSubmitButton"]');
                                if (btn) {{
                                    btn.click();
                                }} else {{
                                    ta.dispatchEvent(new KeyboardEvent('keydown', {{
                                        bubbles: true, cancelable: true, keyCode: 13, key: 'Enter'
                                    }}));
                                }}
                            }}, 100);
                        }}
                        status.innerText = "Befehl übermittelt...";
                        fullCommand = "";
                        isListeningCommand = false;
                    }}
                }}, 1100);
            }}
        }}
    }};

    rec.onend = () => {{
        if (active && !isSpeaking && !isSleep) {{
            try {{ rec.start(); }} catch(e) {{}}
        }}
    }};
}}
</script>
"""

components.html(hud_html, height=52)

for msg in st.session_state.messages[1:]:
    role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
    content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
    if role in ["user", "assistant"] and content:
        with st.chat_message(role):
            st.write(content)
