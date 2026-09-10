import os
import json
import asyncio
import streamlit as st
import streamlit.components.v1 as components
from groq import Groq
import edge_tts
from jarvis_tools import TOOLS_SCHEMA, TOOL_MAP

st.set_page_config(page_title="J.A.R.V.I.S.", page_icon="🤖", layout="centered")
st.title("J.A.R.V.I.S.")
st.caption("Systemstatus: Online. Bereit für Ihre Anweisungen, Sir.")

# API-Key laden
raw_key = st.secrets.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY", "")
GROQ_API_KEY = raw_key.strip() if raw_key else ""

if not GROQ_API_KEY:
    st.error("API-Key fehlt! Bitte trage deinen GROQ_API_KEY in den Streamlit Secrets ein.")
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

SYSTEM_PROMPT = """
Du bist J.A.R.V.I.S., die hochentwickelte KI von Sir.
1. Sprich den Nutzer stets diskret und respektvoll mit 'Sir' an.
2. Sei präzise, loyal, trocken-humorvoll und halte dich extrem kurz (1-2 Sätze).
3. Wenn der Nutzer nach Uhrzeit, Protokollen oder SpielerPlus fragt, rufe sofort die passenden Tools auf.
"""

# Seitenleiste: Standardmäßig AUS
with st.sidebar:
    st.header("Audio-Einstellungen")
    # 1. Beide Schalter standardmäßig auf False (AUS)
    enable_wakeword = st.toggle("🎤 'Hey Jarvis' lauschen", value=False)
    enable_tts = st.toggle("🔊 Sprachausgabe erlauben", value=False)
    voice_option = st.selectbox("Jarvis-Stimme:", ["Deutsch (Conrad)", "Englisch (Ryan)"])

    st.divider()
    if available_models:
        default_idx = available_models.index("openai/gpt-oss-120b") if "openai/gpt-oss-120b" in available_models else 0
        MODEL_NAME = st.selectbox("Aktives Modell:", available_models, index=default_idx)
    else:
        st.error("Keine Modelle gefunden.")
        st.stop()

    if st.button("Chat zurücksetzen"):
        st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if "pending_voice_cmd" in st.session_state:
            del st.session_state["pending_voice_cmd"]
        st.rerun()

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

# Chat-Verlauf anzeigen
for msg in st.session_state.messages[1:]:
    role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
    content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
    if role in ["user", "assistant"] and content:
        with st.chat_message(role):
            st.write(content)

async def generate_edge_speech(text: str, voice_name: str) -> bytes:
    communicate = edge_tts.Communicate(text, voice_name)
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    return audio_data

def speak_text(text: str):
    try:
        voice = "de-DE-ConradNeural" if "Deutsch" in voice_option else "en-GB-RyanNeural"
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio_bytes = loop.run_until_complete(generate_edge_speech(text, voice))
        st.audio(audio_bytes, format="audio/mp3", autoplay=True)
    except Exception as e:
        st.caption(f"Audioausgabe temporär nicht verfügbar: {e}")

def process_query(user_text, is_voice=False):
    st.session_state.messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.write(user_text)

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
        with st.chat_message("assistant"):
            st.write(reply)

        # SPRACHAUSGABE NUR WENN: Per Sprache gefragt UND TTS aktiviert ist!
        if is_voice and enable_tts and reply:
            speak_text(reply)

    except Exception as e:
        st.error(f"Fehler bei Groq-Anfrage ({MODEL_NAME}): {e}")

# HUD & Robuster Wake-Word Listener
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
        background-color: {'#10b981' if enable_wakeword else '#64748b'};
        box-shadow: 0 0 8px {'#10b981' if enable_wakeword else 'transparent'};
    "></div>
    <span id="hud-status">{'Warte auf "Hey Jarvis"...' if enable_wakeword else 'Mikrofon inaktiv (im Seitenmenü einschalten)'}</span>
    <span id="hud-text" style="margin-left: auto; color: #38bdf8;"></span>
</div>

<script>
const active = {str(enable_wakeword).lower()};
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

if (active && SpeechRecognition) {{
    const rec = new SpeechRecognition();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = 'de-DE';

    const dot = document.getElementById('hud-dot');
    const status = document.getElementById('hud-status');
    const hudText = document.getElementById('hud-text');

    let isListeningCommand = false;
    let silenceTimeout = null;
    let fullCommand = "";

    rec.onresult = (event) => {{
        let interim = "";
        let final = "";

        for (let i = event.resultIndex; i < event.results.length; ++i) {{
            if (event.results[i].isFinal) final += event.results[i][0].transcript;
            else interim += event.results[i][0].transcript;
        }}

        let raw = (final || interim).trim();
        let lower = raw.toLowerCase();

        // 1. Wake-Word Erkennung
        if (!isListeningCommand && (lower.includes("hey jarvis") || lower.includes("jarvis"))) {{
            isListeningCommand = true;
            dot.style.backgroundColor = '#38bdf8';
            dot.style.boxShadow = '0 0 12px #38bdf8';
            status.innerText = "Höre zu, Sir...";
            // Wake-Word aus dem Text entfernen
            raw = raw.replace(/hey jarvis/gi, "").replace(/jarvis/gi, "").trim();
        }}

        // 2. Befehl aufzeichnen nach Wake-Word
        if (isListeningCommand) {{
            if (raw.length > 0) {{
                fullCommand = raw;
                hudText.innerText = '"' + fullCommand + '"';

                // Automatisch absenden nach 1 Sekunde Sprechpause
                clearTimeout(silenceTimeout);
                silenceTimeout = setTimeout(() => {{
                    if (fullCommand.trim().length > 0) {{
                        // Streamlit Input-Element suchen und Event triggern
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
                        setTimeout(() => {{
                            dot.style.backgroundColor = '#10b981';
                            dot.style.boxShadow = '0 0 8px #10b981';
                            status.innerText = 'Warte auf "Hey Jarvis"...';
                            hudText.innerText = "";
                        }}, 2000);
                    }}
                }}, 1100);
            }}
        }}
    }};

    rec.onend = () => {{
        if (active) {{
            try {{ rec.start(); }} catch(e) {{}}
        }}
    }};

    try {{ rec.start(); }} catch(e) {{}}
}}
</script>
"""

components.html(hud_html, height=52)

# Chat-Eingabe (Nimmt getippte Befehle oder automatische Wake-Word-Befehle an)
chat_text = st.chat_input("Befehl eingeben, Sir...")

if chat_text:
    # Erkennen, ob der Befehl aus dem Mikrofon stammt
    if chat_text.startswith("[VOICE]"):
        clean_text = chat_text.replace("[VOICE]", "").strip()
        process_query(clean_text, is_voice=True)
    else:
        # Getippter Chat -> Antwort bleibt stumm (nur Text)
        process_query(chat_text, is_voice=False)
