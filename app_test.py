import logging
import pandas as pd
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from streamlit.testing.v1 import AppTest

TOKEN_DATA = {
    "token": "test-token",
    "name": "Tester",
    "valid_from": "01/01/2020",
    "valid_to": "12/31/2099",
    "comments": "auto-generated",
}


def _dummy_connection():
    conn = MagicMock()
    conn.read.return_value = pd.DataFrame([TOKEN_DATA])
    return conn


def _patch_streamlit(monkeypatch):
    monkeypatch.setattr("streamlit.connection", lambda *args, **kwargs: _dummy_connection())
    monkeypatch.setattr("streamlit.secrets", {"openai_api_key": "sk-test", "assistant_id": "assistant-test"})


def test_chatbot_loads_without_error(monkeypatch):
    _patch_streamlit(monkeypatch)
    at = AppTest.from_file("Chatbot.py")
    at.run()
    assert not at.exception
    assert "test-token" in at.session_state["tokens"]


def test_date_validation_after_import(monkeypatch):
    _patch_streamlit(monkeypatch)
    from Chatbot import check_if_date_string_is_valid

    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)

    assert check_if_date_string_is_valid(today.strftime("%m/%d/%Y"))
    assert check_if_date_string_is_valid(tomorrow.strftime("%m/%d/%Y"))
    assert not check_if_date_string_is_valid(tomorrow.strftime("%m/%d/%Y"), check_valid_to=False)

    assert check_if_date_string_is_valid(12345)


def test_date_validation_handles_past_and_future(monkeypatch):
    _patch_streamlit(monkeypatch)
    from Chatbot import check_if_date_string_is_valid

    future_date = (datetime.now().date() + timedelta(days=10)).strftime("%m/%d/%Y")
    past_date = "01/01/2000"

    assert not check_if_date_string_is_valid(future_date, check_valid_to=False)
    assert not check_if_date_string_is_valid(past_date)


def test_date_validation_raises_on_bad_format(monkeypatch):
    _patch_streamlit(monkeypatch)
    from Chatbot import check_if_date_string_is_valid

    with pytest.raises(ValueError):
        check_if_date_string_is_valid("2024-01-01")


class _DummyText:
    def __init__(self, value):
        self.value = value


class _DummyContent:
    def __init__(self, value):
        self.text = _DummyText(value)


class _DummyDelta:
    def __init__(self, value):
        self.content = [_DummyContent(value)]


class _DummyData:
    def __init__(self, value):
        self.delta = _DummyDelta(value)


class _DummyStreamElement:
    def __init__(self, event, value=""):
        self.event = event
        self.data = _DummyData(value)


def test_process_stream_handles_deltas_and_other_events():
    from Chatbot import process_stream

    stream = [
        _DummyStreamElement("thread.message.delta", "hello"),
        _DummyStreamElement("thread.message.delta", " world"),
        _DummyStreamElement("thread.message.trace"),
    ]
    result = list(process_stream(stream))
    assert result == ["hello", " world", ""]


class _DummyUploadedFile:
    def __init__(self, name: str, data: bytes = b"data"):
        self.name = name
        self._data = data

    def getvalue(self):
        return self._data


def _reset_state(monkeypatch):
    _patch_streamlit(monkeypatch)
    import streamlit as st

    st.session_state.clear()
    st.session_state["tokens"] = {}
    return st


def test_register_uploaded_file_handles_duplicates(monkeypatch):
    st = _reset_state(monkeypatch)
    from Chatbot import register_uploaded_file

    dummy = _DummyUploadedFile("doc.pdf")
    assert register_uploaded_file(dummy)
    assert not register_uploaded_file(dummy)
    assert st.session_state["uploaded_files_status"]["doc.pdf"] is False


def test_upload_pending_files_creates_file_ids(monkeypatch):
    st = _reset_state(monkeypatch)
    from Chatbot import register_uploaded_file, upload_pending_files

    register_uploaded_file(_DummyUploadedFile("doc.pdf"))
    client = MagicMock()
    created = MagicMock(id="file-123")
    client.files.create.return_value = created

    errors = []
    result_ids, result_names = upload_pending_files(client, lambda name, exc: errors.append((name, exc)))
    assert result_ids == ["file-123"]
    assert result_names == ["doc.pdf"]
    assert errors == []
    assert st.session_state["uploaded_files_status"]["doc.pdf"]
    assert st.session_state["file_ids"] == ["file-123"]

    result2_ids, result2_names = upload_pending_files(client, lambda name, exc: errors.append((name, exc)))
    assert result2_ids == []
    assert result2_names == []


def test_upload_pending_files_handles_no_files(monkeypatch):
    _reset_state(monkeypatch)
    from Chatbot import upload_pending_files

    client = MagicMock()
    result_ids, result_names = upload_pending_files(client, lambda name, exc: None)
    assert result_ids == []
    assert result_names == []


def test_upload_pending_files_reports_errors(monkeypatch):
    st = _reset_state(monkeypatch)
    from Chatbot import register_uploaded_file, upload_pending_files

    register_uploaded_file(_DummyUploadedFile("error.docx"))
    client = MagicMock()
    client.files.create.side_effect = ValueError("boom")
    errors = []
    result_ids, result_names = upload_pending_files(client, lambda name, exc: errors.append((name, exc)))
    assert result_ids == []
    assert result_names == []
    assert errors
    assert errors[0][0] == "error.docx"
    assert isinstance(errors[0][1], ValueError)
    assert st.session_state["uploaded_files_status"]["error.docx"] is False
    assert st.session_state.get("file_ids", []) == []


def test_build_attachment_payload_logs_list(monkeypatch, caplog):
    from Chatbot import build_attachment_payload

    caplog.set_level(logging.INFO)
    payload = build_attachment_payload([f"file-{i}" for i in range(1, 4)])
    assert len(payload) == 3
    assert payload[0]["file_id"] == "file-1"
    assert "file-3" in caplog.text


def test_build_response_input_and_extractors():
    from Chatbot import _build_response_input, _extract_assistant_text, _extract_text_from_item

    messages = [
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "Hi"},
    ]
    prompt = "Please analyze"
    items = _build_response_input(messages, prompt)
    assert items[-1]["content"] == prompt
    dummy_response = MagicMock()
    dummy_item = {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "analysis"}],
    }
    dummy_response.output = [dummy_item]
    dummy_response.output_text = "analysis"
    assistant_text = _extract_assistant_text(dummy_response)
    assert assistant_text == "analysis"
    assert _extract_text_from_item(dummy_item) == "analysis"


def test_summarize_response_output():
    from Chatbot import _summarize_response_output

    items = [
        {"id": "msg1", "type": "message", "role": "assistant", "attachments": [1], "content": [{"type": "output_text", "text": "hi"}]},
        {"id": "rs1", "type": "reasoning", "content": []},
    ]
    summary = _summarize_response_output(items)
    assert summary[0]["attachments"] == 1
    assert summary[0]["text"] == "hi"


def test_call_responses_api():
    from Chatbot import call_responses_api

    client = MagicMock()
    client.responses.create = MagicMock()
    prompt_payload = {"id": "pmpt", "version": "1"}
    text_input = [
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "Please analyze"},
    ]
    tools = [{"type": "file_search", "vector_store_ids": ["vs1"]}]
    call_responses_api(client, prompt_payload, text_input, tools)
    client.responses.create.assert_called_once()
