import base64
import email
import json

import pytest

import mail_sender
from mail_stub import StubServer


def _decode(body):
    raw = json.loads(body)["raw"]
    return email.message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))


def test_sends_a_plain_text_message_through_gmail():
    with StubServer() as stub:
        stub.add("POST", "/gmail/v1/users/me/messages/send", body={"id": "g1", "threadId": "t1"})
        result = mail_sender.send_gmail("tok", "me@x.com", ["a@x.com", "b@x.com"], ["c@x.com"], "Héllo", "Body ✓",
                                        base_url=stub.base_url + "/gmail/v1")
        sent = _decode(stub.bodies("POST", "/gmail/v1/users/me/messages/send")[0])
    assert result == {"id": "g1", "thread_id": "t1"}
    assert sent["To"] == "a@x.com, b@x.com" and sent["Cc"] == "c@x.com" and sent["From"] == "me@x.com"
    assert str(email.header.make_header(email.header.decode_header(sent["Subject"]))) == "Héllo"
    assert sent.get_payload(decode=True).decode().strip() == "Body ✓"


@pytest.mark.parametrize("to,subject", [
    (["not-an-address"], "s"), (["a@x.com\nBcc: evil@x.com"], "s"), ([], "s"),
    (["a@x.com"], "line1\r\nBcc: evil@x.com"), (["a@x.com"] * 11, "s")])
def test_rejects_bad_recipients_and_header_injection(to, subject):
    with pytest.raises(mail_sender.SendError):
        mail_sender.send_gmail("tok", "me@x.com", to, [], subject, "b", base_url="http://127.0.0.1:1")
