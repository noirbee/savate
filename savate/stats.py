from abc import ABC, abstractmethod
import socket
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from cyhttp11 import HTTPParser

if TYPE_CHECKING:
    from savate.server import TCPServer


class StatsHandler(ABC):
    def __init__(self, server: "TCPServer", **config: Any) -> None:
        self.server = server
        self.config = config

    @abstractmethod
    def request_in(self, request_parser: HTTPParser, sock: socket.socket) -> None:
        ...

    @abstractmethod
    def request_out(
        self,
        request_parser: HTTPParser,
        sock: socket.socket,
        address: tuple[str, int],
        size: int = 0,
        connect_time: Optional[float] = None,
        status_code: int = 200,
    ) -> None:
        ...


class ApacheLogger(StatsHandler):
    """Simple stat handler that just log requests in an Apache like format."""

    def request_in(self, request_parser: HTTPParser, sock: socket.socket) -> None:
        pass

    def request_out(
        self,
        request_parser: HTTPParser,
        sock: socket.socket,
        address: tuple[str, int],
        size: int = 0,
        connect_time: Optional[float] = None,
        status_code: int = 200,
    ) -> None:
        self.server.logger.info(
            '%s - %s [%s] "%s %s %s" %d %s "%s" "%s"',
            address[0],
            "-",  # FIXME: replace by the username
            datetime.fromtimestamp(self.server.loop.now(),).strftime(
                "%d/%b/%Y:%H:%M:%S +0000"
            ),  # FIXME: make this timezone aware
            request_parser.request_method,
            request_parser.request_path,
            request_parser.http_version,
            status_code,
            size if size > 0 else "-",
            request_parser.headers.get("Referer", "-"),
            request_parser.headers.get("User-Agent", "-"),
        )
