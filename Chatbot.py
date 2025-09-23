from openai import OpenAI, NotFoundError
import streamlit as st
from io import BytesIO
from streamlit_gsheets import GSheetsConnection
import logging
import uuid
from datetime import datetime
from streamlit_extras.bottom_container import bottom

def check_if_date_string_is_valid(date_string, check_valid_to=True):
    if not isinstance(date_string, str):
        return True
    # Convert the string to a datetime object
    date_format = '%m/%d/%Y'
    date_object = datetime.strptime(date_string, date_format).date()

    # Get the current date and time
    current_datetime = datetime.now().date()
    # Compare the two datetime objects
    if check_valid_to:
        if current_datetime > date_object: # like if today is 7/4/2024 and date_object is 3/4/2024 (valid_to)
            return False
    else: # valid_from
        if current_datetime < date_object:
            return False
    return True

# Create a connection object.
_conn = st.connection("gsheets", type=GSheetsConnection, ttl=0)
_df = _conn.read(ttl=0)

st.session_state['tokens'] = {}
for i, row in enumerate(_df.itertuples()):
    if isinstance(row.token, str) and len(row.token):
        st.session_state['tokens'][row.token] = (row.name, row.valid_from, row.valid_to, row.comments)

def process_stream(stream):
    for stream_element in stream:
        if stream_element.event == 'thread.message.delta':
            # placeholder.write('🧙‍♀️: Schreibt dir...')
            yield stream_element.data.delta.content[0].text.value
        else:
            yield ''

with st.sidebar:
    token = st.text_input("Password", key="chatbot_token", type="password")
    ctoken = st.empty()
    if len(token):
        if token not in st.session_state["tokens"]:
            ctoken.info('Password unknown')
        else:
            ctoken.info('Success!')
    else:
        ctoken.info('Please enter your password in the field to continue.')
        
#    openai_api_key = st.text_input("OpenAI-API-Schlüssel", key="chatbot_api_key", type="password")
#    "[Erhalten Sie einen OpenAI-API-Schlüssel](https://platform.openai.com/account/api-keys)"

st.title("💬 Regulation Assistant")
st.caption("🖋️ The regulation assistant helps you understand documents and regulations.")

c1 = st.container()
c2 = st.container()
# placeholder = c2.empty()
with bottom():
    c3 = st.container()
    c4 = st.container()

if c4.button('Reset - click here only if you wish to start a new chat'):
    # Delete all the items in Session state
    for key in st.session_state.keys():
        del st.session_state[key]
if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "assistant", "content": "Hey, please help me understand documents and regulations."}]

avatars = {'assistant': '🧙‍♀️', 'user': '👤'}
for msg in st.session_state.messages:
    c1.chat_message(msg["role"], avatar=avatars[msg["role"]]).write(msg["content"])

if 'file_uploader_key' not in st.session_state:
    st.session_state['file_uploader_key'] = str(uuid.uuid4())

uploaded_files = c3.file_uploader(
    label="Here you can upload all documents relevant to the process, such as your CV, job advertisement or other context.",
    accept_multiple_files=True, key=st.session_state['file_uploader_key']
)

for uploaded_file in uploaded_files:
    filename = uploaded_file.name
    if 'uploaded_files' not in st.session_state:
        st.session_state['uploaded_files'] = {}
        st.session_state['uploaded_files_status'] = {}
    if filename not in st.session_state['uploaded_files']:
        bytes_data = uploaded_file.getvalue()
        file_like_object = BytesIO(bytes_data)
        file_like_object.name = filename
        st.session_state['uploaded_files'][filename] = file_like_object
        st.session_state['uploaded_files_status'][filename] = False 

if prompt := c2.chat_input(placeholder='Your message'):
    if not token:
        c1.info("Please enter your password in the field to continue.")
        ctoken.info('Please enter your password in the field to continue.')
        st.stop()
    if token not in st.session_state["tokens"]:
        c1.info("Passwort unbekannt")
        ctoken.info('Passwort unbekannt')
        st.stop()
    name, valid_from, valid_to, comments = st.session_state["tokens"][token]
    if not check_if_date_string_is_valid(valid_from, check_valid_to=False) or not check_if_date_string_is_valid(valid_to, check_valid_to=True):
        c1.info('Passwort an diesem Datum ungültig')
        ctoken.info('Passwort an diesem Datum ungültig')
        st.stop()
    ctoken.info('Erfolg!')
    c1.chat_message("user", avatar=avatars['user']).write(prompt)
    client = OpenAI(api_key=st.secrets['openai_api_key'])
    thread_id = None
    if "thread" not in st.session_state:
        thread = client.beta.threads.create()
        thread_id = thread.id
        st.session_state["thread"] = thread_id
        #logging.debug(f'thread: {thread_id}')
    else:
        thread_id = st.session_state["thread"]
    for msg in st.session_state.messages:
        message = client.beta.threads.messages.create(
            thread_id=thread_id,
            role=msg["role"],
            content=msg["content"]
        )
        #logging.debug(f'queue messages: {str(message)}')
    if "uploaded_files" in st.session_state:
        for key in st.session_state["uploaded_files"]:
            #logging.debug(f'processing {key} ({st.session_state["uploaded_files_status"][key]})')
            if st.session_state["uploaded_files_status"][key] == False:

                # placeholder.write('🧙‍♀️: Ich analysiere den Inhalt der hochgeladenen Dateien...')
                try:
                    file_response = client.files.create(
                        file=st.session_state["uploaded_files"][key],
                        purpose="assistants"
                    )
                    #logging.debug(f'file response: {str(file_response)}')
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
                content="Here you can upload all documents relevant to the process, such as your CV, job advertisement or other context.",
                attachments=[
                    {
                        "file_id": message_file_id,
                        "tools": [{"type": "file_search"}]
                    } for message_file_id in st.session_state["file_ids"][-20:] # just last 20 due to openai limits
                ]
            )
            #logging.debug(f'files message: {str(message)}')
    message = client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=prompt
    )
    #logging.debug(f'final message: {str(message)}')
    st.session_state.messages.append({"role": "user", "content": prompt})
    # placeholder.write('🧙‍♀️: Ich bereite eine Antwort vor...')
    with c1.chat_message("assistant", avatar=avatars['assistant']):
        try:
            with client.beta.threads.runs.stream(
            thread_id=thread_id,
            assistant_id=st.secrets['assistant_id']
            ) as stream:
                msg = st.write_stream(process_stream(stream))
                # msg = st.write_stream(process_stream(stream, placeholder))
            st.session_state.messages.append({"role": "assistant", "content": msg})
        except NotFoundError as e:
            c2.error(f' {e.message} - Most likely you provided a wrong openai api key', icon="🚨")
            st.write(f' 🚨 Error - Most likely you provided a wrong openai api key')
    #logging.debug(f'list messages from session: {str(st.session_state.messages)}')
    # placeholder.empty()
