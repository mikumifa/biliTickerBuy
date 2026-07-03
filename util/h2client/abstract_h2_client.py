from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Protocol


class H2Headers(Protocol):
    def __setitem__(self, key: str, value: str) -> None: ...


class H2Cookies(Protocol):
    def set(
        self,
        name: str,
        value: str,
        domain: str = "",
        path: str = "/",
    ) -> None: ...


class H2Response(Protocol):
    status_code: int
    text: str
    url: Any
    headers: Any

    def json(self) -> Any: ...

    def raise_for_status(self) -> None: ...


class AbstractH2Client(ABC):
    """BiliRequest only needs headers, cookies, head/get/post, and close."""

    @property
    @abstractmethod
    def headers(self) -> H2Headers:
        raise NotImplementedError

    @property
    @abstractmethod
    def cookies(self) -> H2Cookies:
        raise NotImplementedError

    @abstractmethod
    def head(self, url: str) -> H2Response:
        raise NotImplementedError

    @abstractmethod
    def get(self, url: str, *, params: Any = None) -> H2Response:
        raise NotImplementedError

    @abstractmethod
    def post(
        self,
        url: str,
        *,
        data: Any = None,
        json: Any = None,
    ) -> H2Response:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


H2ClientConstructor = Callable[..., AbstractH2Client]
