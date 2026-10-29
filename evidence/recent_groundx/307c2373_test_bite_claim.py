import typing
from unittest.mock import patch

import pytest

from groundx.extract.services.status import Status


class _Logger:
    def info_msg(self, *_a: typing.Any, **_k: typing.Any) -> None:
        pass


class _Cfg:
    service = "s"
    workers = 1

    def __init__(self, url: str) -> None:
        self.url = url

    def status_broker(self) -> str:
        return self.url


@pytest.mark.parametrize(
    "url,db",
    [
        ("redis://h:6379/3", 3),
        ("redis://h:6379", 0),
        ("redis://h:6379/", 0),
        ("redis://h:6379/abc", 0),
        ("redis://h:6379/²", 0),
        ("redis://h:6379/٣", 3),
    ],
)
def test_db_from_url(url: str, db: int) -> None:
    with patch("redis.Redis") as r:
        Status(_Cfg(url), _Logger())  # type: ignore[arg-type]
    assert r.call_args.kwargs["db"] == db
