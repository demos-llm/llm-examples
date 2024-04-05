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
message = st.chat_message("assistant")
if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "assistant", "content": "Hallo, möchten Sie, dass ich Ihnen helfe, das perfekte Anschreiben für Sie zu verfassen?"}]

avatars = {'assistant': '🧙‍♀️', 'user': '👤'}
for msg in st.session_state.messages:
    st.chat_message(msg["role"], avatar=avatars[msg["role"]]).write(msg["content"])

if prompt := st.chat_input(placeholder='Ihre Nachricht'):
    if not openai_api_key:
        st.info("Bitte fügen Sie Ihren OpenAI-API-Schlüssel hinzu, um fortzufahren.")
        st.stop()

    client = OpenAI(api_key=openai_api_key)
    thread = client.beta.threads.create()
    message = client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=prompt
    )
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user", avatar=avatars['user']).write(prompt)
    with st.chat_message("assistant", avatar=avatars['assistant']):
        with client.beta.threads.runs.stream(
        thread_id=thread.id,
        assistant_id='asst_WxG5MfdQBpkaZ7kzT5iuYoWp'
        ) as stream:
            msg = st.write_stream(process_stream(stream))
    st.session_state.messages.append({"role": "assistant", "content": msg})
