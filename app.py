import os
import json
import asyncio
import io
import streamlit as st
import streamlit.components.v1 as components
from groq import Groq
import edge_tts
from jarvis_tools import TOOLS_SCHEMA, TOOL_MAP

st.set_page_config(page_title="J.A.R.V.I.S.", page_icon="🤖", layout="centered")
st.title("J.A.R.V.I.S.")
st.caption("Systemstatus: Online. Bereit für Ihre Anweisungen, Sir.")

# Groq API-Key laden
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

# Seitenleiste: Einstellungen
with st.sidebar:
    st.header("Audio & Sensoren")
    
    # 1. ZUHÖREN: Standardmäßig AUSgeschaltet (value=False)
    enable_wakeword = st.toggle("🎤 Raum abhören ('Hey Jarvis')", value=False)
    
    # 2. STIMMAUSWAHL
    enable_tts = st.toggle("🔊 Sprachausgabe aktiv", value=True)
    voice_option = st.selectbox(
        "Jarvis-Stimme:",
        [
            "Deutsch (Conrad - Souverän/Tief)", 
            "Englisch (Ryan - Britischer Jarvis-Originalton)"
        ]
    )
    
    st.divider()
    st.header("Modell")
    if available_models:
        default_idx = available_models.index("openai/gpt-oss-120b") if "openai/gpt-oss-120b" in available_models else 0
        MODEL_NAME = st.selectbox("Aktives Modell:", available_models, index=default_idx)
    else:
        st.error("Keine Modelle gefunden.")
        st.stop()

    if st.button("Chat zurücksetzen"):
        st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
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
    """Erzeugt hochwertige neuronale Sprachausgabe via edge-tts."""
    communicate = edge_tts.Communicate(text, voice_name)
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    return audio_data

def speak_text(text: str):
    """Spielt die Jarvis-Stimme automatisch ab."""
    try:
        # Ausgewählte Stimme zuweisen
        voice = "de-DE-ConradNeural" if "Deutsch" in voice_option else "en-GB-RyanNeural"
        
        # Audio asynchron erzeugen
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio_bytes = loop.run_until_complete(generate_edge_speech(text, voice))
        
        st.audio(audio_bytes, format="audio/mp3", autoplay=True)
    except Exception as e:
        st.caption(f"Audioausgabe temporär nicht verfügbar: {e}")

def process_query(user_text):
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

        if enable_tts and reply:
            speak_text(reply)

    except Exception as e:
        st.error(f"Fehler bei Groq-Anfrage ({MODEL_NAME}): {e}")

# HTML5 Web Speech Wake-Word-Engine (Wird NUR aktiv wenn Toggle an ist)
if enable_wakeword:
    components.html("""
    <script>
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
        const recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = false;
        recognition.lang = 'de-DE';

        recognition.onresult = function(event) {
            const last = event.results.length - 1;
            const text = event.results[last][0].transcript.trim().toLowerCase();
            
            if (text.includes("jarvis") || text.includes("hey jarvis")) {
                const chatInput = window.parent.document.querySelector('textarea[data-testid="stChatInputTextArea"]');
                if (chatInput) {
                    chatInput.value = text;
                    chatInput.dispatchEvent(new Event('input', { bubbles: true }));
                    const enterEvent = new KeyboardEvent('keydown', {
                        bubbles: true, cancelable: true, keyCode: 13, key: 'Enter'
                    });
                    chatInput.dispatchEvent(enterEvent);
                }
            }
        };

        recognition.onend = function() {
            recognition.start();
        };

        recognition.start();
    }
    </script>
    """, height=0)

# Eingaben
voice_audio = st.audio_input("Sprachnachricht aufnehmen")
chat_text = st.chat_input("Befehl eingeben, Sir...")

if chat_text:
    process_query(chat_text)

if voice_audio:
    try:
        transcription = client.audio.transcriptions.create(
            file=("voice.wav", voice_audio.read()),
            model="whisper-large-v3"
        ).text
        if transcription.strip():
            process_query(transcription)
    except Exception as e:
        st.error(f"Fehler bei Audio-Verarbeitung: {e}")
