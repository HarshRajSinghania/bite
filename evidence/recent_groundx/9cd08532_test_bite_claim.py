import pytest
from unittest.mock import MagicMock

from groundx.extract.services.status import Status


@pytest.mark.parametrize(
    "url",
    [
        "redis://h:6379/" + "9" * 5000,
        "redis://h/\u0663",
        "redis://h:\u00b2/0",
        "host:\u00b2",
        "redis://host:\u00b2",
        "redis:///0\u00b2",
        "",
        "::::",
    ],
)
def test_status_never_crashes(url):
    cfg = MagicMock()
    cfg.status_broker.return_value = url
    Status(cfg, MagicMock())
