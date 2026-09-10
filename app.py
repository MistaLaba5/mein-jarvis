import os
import json
import asyncio
import streamlit as st
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

# Seitenleiste: Einstellungen
with st.sidebar:
    st.header("Audio & Modell")
    enable_tts = st.toggle("🔊 Sprachausgabe aktiv", value=True)
    voice_option = st.selectbox(
        "Jarvis-Stimme:",
        ["Deutsch (Conrad)", "Englisch (Ryan)"]
    )
    
    st.divider()
    if available_models:
        default_idx = available_models.index("openai/gpt-oss-120b") if "openai/gpt-oss-120b" in available_models else 0
        MODEL_NAME = st.selectbox("Aktives Modell:", available_models, index=default_idx)
    else:
        st.error("Keine Modelle gefunden.")
        st.stop()

    if st.button("Chat zurücksetzen"):
        st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if "last_processed_audio" in st.session_state:
            del st.session_state["last_processed_audio"]
        st.rerun()

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

# Chat-Verlauf rendern
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

# HUD-Statusleiste
st.markdown("""
<div style="
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 14px;
    margin-bottom: 12px;
    border-radius: 6px;
    background: #111827;
    border: 1px solid #1f2937;
    color: #94a3b8;
    font-size: 13px;
">
    <div style="width: 8px; height: 8px; border-radius: 50%; background: #10b981; box-shadow: 0 0 6px #10b981;"></div>
    <span>Audio-Interface bereit. Sprechen oder tippen.</span>
</div>
""", unsafe_allow_html=True)

# 1. Spracheingabe: Streamlits nativer Audio-Recorder
audio_file = st.audio_input("Befehl per Sprache aufnehmen")

if audio_file is not None:
    audio_bytes = audio_file.read()
    # Verhindert doppeltes Verarbeiten desselben Audios beim Re-Render
    if st.session_state.get("last_processed_audio") != audio_bytes:
        st.session_state["last_processed_audio"] = audio_bytes
        with st.spinner("Transkribiere Sprache..."):
            try:
                transcription = client.audio.transcriptions.create(
                    file=("voice.wav", audio_bytes),
                    model="whisper-large-v3"
                ).text
                if transcription.strip():
                    process_query(transcription)
            except Exception as e:
                st.error(f"Fehler bei Audio-Verarbeitung: {e}")

# 2. Texteingabe
chat_text = st.chat_input("Befehl eingeben, Sir...")
if chat_text:
    process_query(chat_text)
