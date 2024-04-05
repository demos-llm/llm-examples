from openai import OpenAI
import streamlit as st

def process_stream(stream):
    for stream_element in stream:
        if stream_element.event == 'thread.message.delta':
            yield stream_element.data.delta.content[0].text.value
        else:
            yield ''

with st.sidebar:
    openai_api_key = st.text_input("OpenAI-API-Schlüssel", key="chatbot_api_key", type="password")
    "[Erhalten Sie einen OpenAI-API-Schlüssel](https://platform.openai.com/account/api-keys)"

st.title("💬 Anschreiben Assistant")
st.caption("🖋️ Der Anschreiben Assistant generiert ein ideales Anschreiben für dich")
if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "assistant", "content": "Hallo, möchten Sie, dass ich Ihnen helfe, das perfekte Anschreiben für Sie zu verfassen?"}]

avatars = {'assistant': '🧙‍♀️', 'user': '👤'}
for msg in st.session_state.messages:
    st.chat_message(msg["role"], avatar=avatars[msg["role"]]).write(msg["content"])

uploaded_file = st.file_uploader("Wähle eine Datei")
if uploaded_file is not None:
    bytes_data = uploaded_file.getvalue()
    if "uploaded_file" not in st.session_state or not st.session_state["uploaded_file"]:
        st.session_state["uploaded_file"] = bytes_data

if prompt := st.chat_input(placeholder='Ihre Nachricht'):
    if not openai_api_key:
        st.info("Bitte fügen Sie Ihren OpenAI-API-Schlüssel hinzu, um fortzufahren.")
        st.stop()

    client = OpenAI(api_key=openai_api_key)
    thread_id = None
    if "thread" not in st.session_state:
        thread = client.beta.threads.create()
        thread_id = thread.id
        st.session_state["thread"] = thread_id
    else:
        thread_id = st.session_state["thread"]
    for msg in st.session_state.messages:
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role=msg["role"],
            content=msg["content"]
        )
    if "uploaded_file" in st.session_state and st.session_state["uploaded_file"]:
        bytes_data = st.session_state["uploaded_file"]
        file_response = client.files.create(
            file=bytes_data,
            purpose="assistants"
        )

        message = client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=prompt,
            file_ids = [file_response.id]
        )
        
        st.session_state["uploaded_file"] = None
    else:
        message = client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=prompt
        )
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar=avatars['user']).write(prompt)
    with st.chat_message("assistant", avatar=avatars['assistant']):
        with client.beta.threads.runs.stream(
        thread_id=thread_id,
        assistant_id='asst_WxG5MfdQBpkaZ7kzT5iuYoWp'
        ) as stream:
            msg = st.write_stream(process_stream(stream))
    st.session_state.messages.append({"role": "assistant", "content": msg})
