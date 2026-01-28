from openai import OpenAI, NotFoundError
import streamlit as st
from io import BytesIO
from streamlit_gsheets import GSheetsConnection
import logging
import uuid
from datetime import datetime
from streamlit_extras.bottom_container import bottom
from typing import Callable, Iterable

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


def _ensure_upload_state():
    if "uploaded_files" not in st.session_state:
        st.session_state["uploaded_files"] = {}
        st.session_state["uploaded_files_status"] = {}


def register_uploaded_file(uploaded_file) -> bool:
    _ensure_upload_state()
    filename = uploaded_file.name
    if filename in st.session_state["uploaded_files"]:
        return False
    bytes_data = uploaded_file.getvalue()
    file_like_object = BytesIO(bytes_data)
    file_like_object.name = filename
    st.session_state["uploaded_files"][filename] = file_like_object
    st.session_state["uploaded_files_status"][filename] = False
    return True


def upload_pending_files(client, on_error: Callable[[str, Exception], None]):
    uploaded_files = st.session_state.get("uploaded_files")
    if not uploaded_files:
        return [], []
    statuses = st.session_state.setdefault("uploaded_files_status", {})
    new_ids = []
    new_names = []
    for key, file_obj in uploaded_files.items():
        if statuses.get(key):
            continue
        try:
            file_response = client.files.create(
                file=file_obj,
                purpose="assistants"
            )
            statuses[key] = True
            new_ids.append(file_response.id)
            new_names.append(key)
        except Exception as exc:
            on_error(key, exc)
    if new_ids:
        st.session_state.setdefault("file_ids", []).extend(new_ids)
    return new_ids, new_names


def build_attachment_payload(file_ids: Iterable[str]) -> list[dict]:
    ids = list(file_ids)
    payload = [
        {"file_id": file_id, "tools": [{"type": "file_search"}]}
        for file_id in ids[-20:]
    ]
    logging.info("Built attachment payload for file_ids=%s", ids[-20:])
    return payload


def _build_response_input(messages: list[dict], prompt: str) -> list[dict]:
    items = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in messages
    ]
    items.append({"role": "user", "content": prompt})
    return items


def _extract_text_from_item(item: dict) -> str:
    content = item.get("content", [])
    if not isinstance(content, list):
        return ""
    return "\n".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "output_text"
    )


def _summarize_response_output(output_items: list[dict]) -> list[dict]:
    summaries = []
    for item in output_items:
        summaries.append({
            "id": item.get("id"),
            "type": item.get("type"),
            "role": item.get("role"),
            "attachments": len(item.get("attachments", [])),
            "text": _extract_text_from_item(item),
        })
    return summaries


def _extract_assistant_text(response) -> str:
    if hasattr(response, "output_text") and response.output_text:
        return response.output_text
    output_items = getattr(response, "output", [])
    for item in output_items:
        if item.get("type") == "message" and item.get("role") == "assistant":
            text = _extract_text_from_item(item)
            if text:
                return text
    return ""


def call_responses_api(client, prompt_payload, text_input, tools):
    return client.responses.create(
        prompt=prompt_payload,
        input=text_input,
        include=["output", "output_text"],
        tools=tools or None,
        store=False
    )

# Create a connection object.
_df = None
try:
    _conn = st.connection("gsheets", type=GSheetsConnection, ttl=0)
    _df = _conn.read(ttl=0)
except ValueError:
    logging.warning("Spreadsheet connection could not be initialized; proceeding with empty tokens.")

st.session_state['tokens'] = {}
if _df is not None:
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

avatars = {'assistant': '🧙‍♀️', 'user': '👤', 'system': '🖥️'}
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
    register_uploaded_file(uploaded_file)

if prompt := c2.chat_input(placeholder='Your message'):
    if not token:
        c1.info("Please enter your password in the field to continue.")
        ctoken.info('Please enter your password in the field to continue.')
        st.stop()
    if token not in st.session_state["tokens"]:
        c1.info("Password incorrect")
        ctoken.info('Password incorrect')
        st.stop()
    name, valid_from, valid_to, comments = st.session_state["tokens"][token]
    if not check_if_date_string_is_valid(valid_from, check_valid_to=False) or not check_if_date_string_is_valid(valid_to, check_valid_to=True):
        c1.info('Password expired')
        ctoken.info('Password expired')
        st.stop()
    ctoken.info('Success!')
    c1.chat_message("user", avatar=avatars['user']).write(prompt)
    client = OpenAI(api_key=st.secrets['openai_api_key'])
    def _report_upload_error(filename, exc):
        logging.error("Failed to upload %s: %s", filename, exc)
        c1.chat_message('system', avatar=avatars['system']).write(f"Upload error for {filename}: {exc}")

    new_ids, new_names = upload_pending_files(client, _report_upload_error)
    if new_names:
        c1.chat_message('system', avatar=avatars['system']).write(f"File uploaded: {', '.join(new_names)}")
    attachments = build_attachment_payload(st.session_state.get("file_ids", []))
    if attachments:
        c1.chat_message('system', avatar=avatars['system']).write(
            f"Attach {len(attachments)} file(s) to the upcoming prompt: {[entry['file_id'] for entry in attachments]}"
        )
    tools = []
    if attachments:
        vector_store_ids = st.secrets.get("vector_store_ids", [])
        if vector_store_ids:
            tools.append({
                "type": "file_search",
                "vector_store_ids": vector_store_ids,
            })
    prompt_payload = {
        "id": st.secrets.get("prompt_id", "pmpt_6979c830bf4c8197a48f1197b963078108d22efa081cae2a"),
        "version": (st.secrets.get("prompt_version") or "1"),
    }
    user_input = prompt + (f" (Attachments used: {[entry['file_id'] for entry in attachments]})" if attachments else "")
    response = None
    try:
        response = call_responses_api(client, prompt_payload, _build_response_input(st.session_state["messages"], user_input), tools)
        logging.info("Responses API result: %s", response)
        output_summary = _summarize_response_output(getattr(response, "output", []))
        c1.chat_message('system', avatar=avatars['system']).write(
            f"Response metadata: {output_summary}. Attachment items sent: {[entry['file_id'] for entry in attachments]}"
        )
        assistant_text = _extract_assistant_text(response) or ""
    except Exception as exc:
        logging.error("Responses.create failed: %s", exc)
        c1.chat_message('system', avatar=avatars['system']).write(
            f"Responses API failed: {exc}. Check OpenAI console for more details."
        )
        assistant_text = ""

    st.session_state.messages.append({"role": "user", "content": prompt})
    if assistant_text:
        st.session_state.messages.append({"role": "assistant", "content": assistant_text})
        c1.chat_message("assistant", avatar=avatars['assistant']).write(assistant_text)
