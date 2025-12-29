"""Starlette middleware for response compression.

This middleware supports both GZIP and ZSTD compression, with intelligent
negotiation based on the client's Accept-Encoding header. ZSTD is preferred
over GZIP when both are supported by the client.

Uses Python 3.14's native ZSTD support via the compression.zstd module.
Follows the Starlette GZipMiddleware responder pattern.
"""

from __future__ import annotations

from compression import zstd
from typing import TYPE_CHECKING, Any, override

from starlette.datastructures import Headers
from starlette.middleware.gzip import GZipResponder, IdentityResponder

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


def parse_accept_encoding(header_value: str) -> str | None:
    """Parse Accept-Encoding header and return best supported algorithm.

    Prefers ZSTD over GZIP when both are supported.

    Args:
        header_value: Value of the Accept-Encoding header

    Returns:
        The best compression algorithm to use, or None if no supported algorithm

    Examples:
        >>> parse_accept_encoding("gzip, deflate")
        'gzip'
        >>> parse_accept_encoding("gzip, zstd")
        'zstd'
        >>> parse_accept_encoding("zstd")
        'zstd'
        >>> parse_accept_encoding("deflate")
        None
    """
    # Normalize the header value
    encodings = {enc.strip().lower() for enc in header_value.split(",")}

    # Prefer ZSTD over GZIP
    if "zstd" in encodings:
        return "zstd"
    if "gzip" in encodings:
        return "gzip"

    return None


class ZstdResponder(IdentityResponder):
    """Responder that applies ZSTD compression."""

    content_encoding = "zstd"

    @override
    def __init__(self, app: ASGIApp, minimum_size: int, *, level: int = 22) -> None:
        """Initialize the ZSTD responder.

        Args:
            app: The ASGI application
            minimum_size: Minimum response size in bytes to trigger compression
            level: ZSTD compression level (default 10)
        """
        super().__init__(app, minimum_size)
        self.level = level

    @override
    def apply_compression(self, body: bytes, **kwargs: Any) -> bytes:
        """Apply ZSTD compression to the body.

        Args:
            body: The response body to compress

        Returns:
            The ZSTD-compressed body
        """
        return zstd.compress(body, level=self.level)


class CompressionMiddleware:
    """Middleware that compresses responses using GZIP or ZSTD.

    The middleware automatically detects the best compression algorithm based on
    the Accept-Encoding header. ZSTD is preferred over GZIP when both are supported.
    Responses smaller than the minimum_size are not compressed.
    """

    def __init__(self, app: ASGIApp, *, minimum_size: int = 1000) -> None:
        """Initialize the compression middleware.

        Args:
            app: The ASGI application
            minimum_size: Minimum response size in bytes to trigger compression
        """
        self.app = app
        self.minimum_size = minimum_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle the ASGI request.

        Args:
            scope: The ASGI scope
            receive: The receive callable
            send: The send callable
        """
        if scope["type"] != "http":  # pragma: no cover
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        accept_encoding = headers.get("accept-encoding", "")

        responder: ASGIApp
        match parse_accept_encoding(accept_encoding):
            case "zstd":
                responder = ZstdResponder(self.app, self.minimum_size)
            case "gzip":
                responder = GZipResponder(self.app, self.minimum_size)
            case _:
                responder = IdentityResponder(self.app, self.minimum_size)

        await responder(scope, receive, send)
