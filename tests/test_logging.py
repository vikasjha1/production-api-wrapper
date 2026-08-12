import json
import logging

from app.core.logging import JSONFormatter


def test_formatter_includes_standard_fields() -> None:
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="something happened",
        args=(),
        exc_info=None,
    )
    record.request_id = "abc-123"

    output = json.loads(formatter.format(record))

    assert output["message"] == "something happened"
    assert output["level"] == "INFO"
    assert output["logger"] == "test"
    assert output["request_id"] == "abc-123"


def test_formatter_surfaces_extra_fields() -> None:
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="chat_cost",
        args=(),
        exc_info=None,
    )
    record.client_id = "test-client"
    record.cost_usd = 0.0042

    output = json.loads(formatter.format(record))

    assert output["client_id"] == "test-client"
    assert output["cost_usd"] == 0.0042
