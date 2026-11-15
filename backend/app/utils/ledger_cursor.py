"""Versioned, query-bound seek cursors (not authorization credentials)."""

import base64
import binascii
import hashlib
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID


def query_scope(*parts: str) -> str:
    return hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()


def encode_cursor(scope: str, value: object, record_id: str) -> str:
    payload = [1, scope, None if value is None else str(value), record_id]
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")


def decode_cursor(token: str, scope: str, sort: str) -> tuple[object, str]:
    try:
        if not token or len(token) > 2048:
            raise ValueError
        data = json.loads(base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True))
        if not isinstance(data, list) or len(data) != 4 or data[:2] != [1, scope]:
            raise ValueError
        value, record_id = data[2:]
        if not isinstance(record_id, str) or str(UUID(record_id)) != record_id:
            raise ValueError
        if value is not None:
            if not isinstance(value, str) or len(value) > 128:
                raise ValueError
            if sort == "date":
                value = datetime.fromisoformat(value)
            elif sort != "bank_utr":
                value = Decimal(value)
                if not value.is_finite() or value.copy_abs() > Decimal("9999999999999999.99"):
                    raise ValueError
        elif sort != "rzp_amount" and sort != "bank_utr":
            raise ValueError
        return value, record_id
    except (ValueError, TypeError, InvalidOperation, binascii.Error, UnicodeError) as exc:
        raise ValueError("Invalid cursor or cursor does not match the selected filters/sort") from exc
