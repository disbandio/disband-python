import base64
import hashlib
import hmac
import os
import time
from collections.abc import Mapping

from ._errors import DisbandError, WebhookVerificationError
from ._models import Failed, Ready, ended_adapter

# Standard Webhooks: HMAC-SHA256 over "id.timestamp.body", the secret written as whsec_ and its base64
_tolerance = 5 * 60


def webhook_secret(api_key: str) -> str:
    """Return the webhook secret of an API key, the same as when the key was created."""
    mac = hmac.new(api_key.encode(), b"disband webhooks", hashlib.sha256).digest()
    return "whsec_" + base64.b64encode(mac).decode()


def verify_webhook(body: bytes, headers: Mapping[str, str], secret: str | None = None) -> Ready | Failed:
    """Verify a webhook and return the separation it posted.

    `body` is the request body as received, before any parsing, and `headers` the request's headers in any case.
    `secret` defaults to `DISBAND_WEBHOOK_SECRET`. Raise `WebhookVerificationError` when the signature or its
    timestamp doesn't verify.
    """
    secret = secret if secret is not None else os.environ.get("DISBAND_WEBHOOK_SECRET")
    if not secret:
        raise DisbandError("Neither secret nor DISBAND_WEBHOOK_SECRET is set")
    named = {name.lower(): value for name, value in headers.items()}
    webhook_id = named.get("webhook-id")
    timestamp = named.get("webhook-timestamp")
    signatures = named.get("webhook-signature")
    if webhook_id is None or timestamp is None or signatures is None:
        raise WebhookVerificationError("The webhook headers are missing")
    # whatever a forger sends is refused, never raised as another error
    if not (timestamp.isascii() and timestamp.isdigit()) or abs(time.time() - int(timestamp)) > _tolerance:
        raise WebhookVerificationError("The webhook's timestamp is too old or invalid")
    # with or without its prefix, as Standard Webhooks libraries take it
    key = base64.b64decode(secret.removeprefix("whsec_"))
    mac = hmac.new(key, f"{webhook_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()
    expected = base64.b64encode(mac)
    for entry in signatures.split(" "):
        version, _, signature = entry.partition(",")
        # as bytes, since compare_digest refuses a str beyond ASCII
        if version == "v1" and hmac.compare_digest(signature.encode(), expected):
            return ended_adapter.validate_json(body)
    raise WebhookVerificationError("No webhook signature matches")
