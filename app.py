import os
import json
import streamlit as st
from groq import Groq
from jarvis_tools import TOOLS_SCHEMA, TOOL_MAP

st.set_page_config(page_title="J.A.R.V.I.S.", page_icon="🤖", layout="centered")
st.title("J.A.R.V.I.S. // Online Core")
st.caption("Systemstatus: Online. Bereit für Ihre Anweisungen, Sir.")

# Groq API-Key sicher und ohne versehentliche Leerzeichen laden
raw_key = st.secrets.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY", "")
GROQ_API_KEY = raw_key.strip() if raw_key else ""

if not GROQ_API_KEY:
    st.error("API-Key fehlt! Bitte trage deinen GROQ_API_KEY in den Streamlit Secrets ein.")
    st.stop()

# Explizite Übergabe von base_url verhindert den 404-Fehler
client = Groq(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com"
)

MODEL_NAME = "llama-3.1-70b-versatile"

SYSTEM_PROMPT = """
Du bist J.A.R.V.I.S., die hochentwickelte KI von Sir.
1. Sprich den Nutzer stets diskret und respektvoll mit 'Sir' an.
2. Sei präzise, loyal, trocken-humorvoll und halte dich extrem kurz (1-2 Sätze).
3. Wenn der Nutzer nach Uhrzeit, Protokollen oder SpielerPlus fragt, rufe sofort die passenden Tools auf.
"""

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

for msg in st.session_state.messages[1:]:
    if msg["role"] in ["user", "assistant"] and msg.get("content"):
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

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
            st.session_state.messages.append(response_message)
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

    except Exception as e:
        st.error(f"Fehler bei Groq-Anfrage: {e}")

col1, col2 = st.columns([4, 1])
with col1:
    chat_text = st.chat_input("Befehl eingeben, Sir...")
with col2:
    voice_audio = st.audio_input("Sprache")

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
