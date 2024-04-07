from openai import OpenAI, NotFoundError
import streamlit as st
from streamlit_gsheets import GSheetsConnection
import logging
import uuid

# Create a connection object.
conn = st.connection("gsheets", type=GSheetsConnection)
df = conn.read()

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
st.secrets["connections.gsheets"]["spreadsheet"]

# Print results.
for i, row in enumerate(df.itertuples()):
    st.write(f"{i} - {row.name}: {row.comments}")
    

c1 = st.container()
c2 = st.container()
c3 = st.container()
c4 = st.container()

if c4.button('Zurücksetzen – klicken Sie hier nur, wenn Sie von vorne beginnen möchten', type='primary'):
    # Delete all the items in Session state
    for key in st.session_state.keys():
        del st.session_state[key]
if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "assistant", "content": "Hallo, möchten Sie, dass ich Ihnen helfe, das perfekte Anschreiben für Sie zu verfassen?"}]

avatars = {'assistant': '🧙‍♀️', 'user': '👤'}
for msg in st.session_state.messages:
    c1.chat_message(msg["role"], avatar=avatars[msg["role"]]).write(msg["content"])

if 'file_uploader_key' not in st.session_state:
    st.session_state['file_uploader_key'] = str(uuid.uuid4())

uploaded_files = c3.file_uploader(
    label="Hier können Sie alle für den Prozess relevanten Dokumente wie Lebenslauf, Stellenausschreibung oder anderen Kontext hochladen",
    accept_multiple_files=True, key=st.session_state['file_uploader_key']
)

for uploaded_file in uploaded_files:
    filename = uploaded_file.name
    if 'uploaded_files' not in st.session_state:
        st.session_state['uploaded_files'] = {}
        st.session_state['uploaded_files_status'] = {}
    if filename not in st.session_state['uploaded_files']:
        bytes_data = uploaded_file.getvalue()
        st.session_state['uploaded_files'][filename] = bytes_data
        st.session_state['uploaded_files_status'][filename] = False 

if prompt := c2.chat_input(placeholder='Ihre Nachricht'):
    if not openai_api_key:
        c1.info("Bitte fügen Sie Ihren OpenAI-API-Schlüssel hinzu, um fortzufahren.")
        st.stop()
    c1.chat_message("user", avatar=avatars['user']).write(prompt)
    
    client = OpenAI(api_key=openai_api_key)
    thread_id = None
    if "thread" not in st.session_state:
        thread = client.beta.threads.create()
        thread_id = thread.id
        st.session_state["thread"] = thread_id
        logging.error(f'thread: {thread_id}')
    else:
        thread_id = st.session_state["thread"]
    for msg in st.session_state.messages:
        message = client.beta.threads.messages.create(
            thread_id=thread_id,
            role=msg["role"],
            content=msg["content"]
        )
        logging.error(f'queue messages: {str(message)}')
    if "uploaded_files" in st.session_state:
        for key in st.session_state["uploaded_files"]:
            logging.error(f'processing {key} ({st.session_state["uploaded_files_status"][key]})')
            if st.session_state["uploaded_files_status"][key] == False:
                try:
                    file_response = client.files.create(
                        file=st.session_state["uploaded_files"][key],
                        purpose="assistants"
                    )
                    logging.error(f'file response: {str(file_response)}')
                    st.session_state["uploaded_files_status"][key] = True
                    if "file_ids" not in st.session_state:
                        st.session_state["file_ids"] = []
                    st.session_state["file_ids"].append(file_response.id)
                except Exception:
                    pass
        if "file_ids" in st.session_state and len(st.session_state["file_ids"]):
            message = client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content="Hier habe ich einige für den Prozess relevante Dokumente wie Lebenslauf, Stellenanzeige oder anderen Kontext hochgeladen – bitte finden Sie heraus, was diese Dateien darstellen.",
                file_ids = st.session_state["file_ids"][-10:]  # just last 10 due to openai limits
            )
            logging.error(f'files message: {str(message)}')
    message = client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=prompt
    )
    logging.error(f'final message: {str(message)}')
    st.session_state.messages.append({"role": "user", "content": prompt})
    with c1.chat_message("assistant", avatar=avatars['assistant']):
        try:
            with client.beta.threads.runs.stream(
            thread_id=thread_id,
            assistant_id='asst_WxG5MfdQBpkaZ7kzT5iuYoWp'
            ) as stream:
                msg = st.write_stream(process_stream(stream))
            st.session_state.messages.append({"role": "assistant", "content": msg})
        except NotFoundError as e:
            c2.error(f' {e.message} - Most likely you provided a wrong openai api key', icon="🚨")
            st.write(f' 🚨 Error - Most likely you provided a wrong openai api key')
    logging.error(f'list messages from session: {str(st.session_state.messages)}')