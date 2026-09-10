import os
import json
import streamlit as st
from groq import Groq
from jarvis_tools import TOOLS_SCHEMA, TOOL_MAP

st.set_page_config(page_title="J.A.R.V.I.S.", page_icon="🤖", layout="centered")
st.title("J.A.R.V.I.S. // Online Core")
st.caption("Systemstatus: Online. Bereit für Ihre Anweisungen, Sir.")

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

if available_models:
    # Standardmäßig openai/gpt-oss-120b wählen, falls in der Liste vorhanden
    default_idx = available_models.index("openai/gpt-oss-120b") if "openai/gpt-oss-120b" in available_models else 0
    MODEL_NAME = st.sidebar.selectbox("Aktives Groq-Modell:", available_models, index=default_idx)
else:
    st.error("Keine verfügbaren Modelle für diesen API-Key gefunden.")
    st.stop()
# Reset-Button in der Seitenleiste
if st.sidebar.button("Chat zurücksetzen"):
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    st.rerun()

SYSTEM_PROMPT = """
Du bist J.A.R.V.I.S., die hochentwickelte KI von Sir.
1. Sprich den Nutzer stets diskret und respektvoll mit 'Sir' an.
2. Sei präzise, loyal, trocken-humorvoll und halte dich extrem kurz (1-2 Sätze).
3. Wenn der Nutzer nach Uhrzeit, Protokollen oder SpielerPlus fragt, rufe sofort die passenden Tools auf.
"""

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

# Sicherer Chat-Verlauf: Funktioniert mit Objekten und Dictionaries
for msg in st.session_state.messages[1:]:
    role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
    content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
    if role in ["user", "assistant"] and content:
        with st.chat_message(role):
            st.write(content)

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
            # Bereinigte Tool-Call-Liste ohne störende Zusatzattribute
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

            # Nur die von Groq erlaubten Felder anhängen (keine annotations o.ä.)
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

    except Exception as e:
        st.error(f"Fehler bei Groq-Anfrage ({MODEL_NAME}): {e}")
