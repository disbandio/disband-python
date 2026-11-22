import json
import time
from datetime import UTC, datetime

import pytest
from standardwebhooks.webhooks import Webhook

from disband import DisbandError, WebhookVerificationError, verify_webhook, webhook_secret
from tests.fake import ready

example_key = "disband_EXAMPLEexampleEXAMPLEexampleEXAMPLE00"
example_secret = "whsec_MeFukvonQ5URJghmuKcsZq13z3KhKzPTJ6iSpp/Cfo8="


def signed(secret: str, body: bytes, at: datetime | None = None) -> dict[str, str]:
    at = at or datetime.now(tz=UTC)
    signature = Webhook(secret).sign("sep_test", at, body.decode())
    return {"Webhook-Id": "sep_test", "Webhook-Timestamp": str(int(at.timestamp())), "Webhook-Signature": signature}


def test_a_keys_webhook_secret_matches_the_docs_example():
    assert webhook_secret(example_key) == example_secret


def test_a_signed_webhook_verifies_from_headers_in_any_case():
    body = json.dumps(ready()).encode()
    separation = verify_webhook(body, signed(example_secret, body), example_secret)
    assert separation.status == "ready"


def test_a_changed_body_or_an_old_timestamp_is_refused():
    body = json.dumps(ready()).encode()
    with pytest.raises(WebhookVerificationError):
        verify_webhook(body + b" ", signed(example_secret, body), example_secret)
    old = datetime.fromtimestamp(time.time() - 600, tz=UTC)
    with pytest.raises(WebhookVerificationError):
        verify_webhook(body, signed(example_secret, body, old), example_secret)


def test_forged_headers_are_refused_never_raised_as_another_error():
    body = json.dumps(ready()).encode()
    headers = signed(example_secret, body)
    with pytest.raises(WebhookVerificationError):
        verify_webhook(body, {**headers, "Webhook-Signature": "v1,é"}, example_secret)
    with pytest.raises(WebhookVerificationError):
        verify_webhook(body, {**headers, "Webhook-Timestamp": "²"}, example_secret)


def test_any_one_matching_signature_verifies():
    body = json.dumps(ready()).encode()
    headers = signed(example_secret, body)
    rotated = {**headers, "Webhook-Signature": f"v1,b2xk {headers['Webhook-Signature']}"}
    assert verify_webhook(body, rotated, example_secret).status == "ready"


def test_a_missing_secret_is_a_setup_error_not_a_forged_webhook(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DISBAND_WEBHOOK_SECRET", raising=False)
    with pytest.raises(DisbandError) as raised:
        verify_webhook(b"{}", {})
    assert not isinstance(raised.value, WebhookVerificationError)
