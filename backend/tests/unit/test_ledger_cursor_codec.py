import base64
import json
from uuid import UUID

import pytest

from app.utils.ledger_cursor import decode_cursor, encode_cursor, query_scope

SCOPE = query_scope("default", "ALL")
ID = str(UUID(int=1))


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e99999999", "10000000000000000"])
def test_untrusted_decimal_position_is_bounded(value):
    with pytest.raises(ValueError, match="Invalid cursor"):
        decode_cursor(encode_cursor(SCOPE, value, ID), SCOPE, "bank_amount")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        [1],
        [2, SCOPE, "2026-01-01", ID],
        [1, SCOPE, None, ID],
        [1, SCOPE, "2026-01-01", "invalid-id"],
        [1, SCOPE, {"nested": "data"}, ID],
    ],
)
def test_cursor_shape_version_and_position_are_validated(payload):
    token = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    with pytest.raises(ValueError):
        decode_cursor(token, SCOPE, "date")
