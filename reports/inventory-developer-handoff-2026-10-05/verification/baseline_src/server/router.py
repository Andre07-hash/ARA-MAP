"""A minimal path router: enough for ~20 local endpoints, nothing more."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlparse

from .errors import ApiError

# Every route handler takes the request and returns either a JSON body or a
# (contents, filename) pair for a download.
Handler = Callable[["Request"], Any]


class Route:
    """One method plus path pattern, bound to its handler."""


    def __init__(self, method: str, pattern: str, handler: Handler) -> None:
        self.method = method
        # ":name" in a path becomes a named integer capture group.
        regex = re.sub(r":(\w+)", r"(?P<\1>[^/]+)", pattern)
        self.pattern = re.compile(f"^{regex}$")
        self.handler = handler


class Request:
    """One inbound request, already parsed into path, query and body."""


    def __init__(
        self,
        method: str,
        path: str,
        query: dict[str, list[str]],
        params: dict[str, str],
        body: bytes,
        headers: Any,
    ) -> None:
        self.method = method
        self.path = path
        self.query = query
        self.params = params
        self.body = body
        self.headers = headers

    def param(self, name: str) -> int:
        """A captured path segment, as an integer id.

        A segment that is not a number means the URL is wrong, not that the
        application broke: /api/bases/abc is a 404, not a 500 with a traceback.
        """
        try:
            return int(self.params[name])
        except (KeyError, ValueError):
            raise ApiError("Ruta no encontrada.", 404) from None

    def q(self, name: str, default: str | None = None) -> str | None:
        """The first value of a query parameter, or the default."""
        values = self.query.get(name)
        return values[0] if values else default


class Router:
    """The route table. Matching is first-registered-wins."""

    def __init__(self) -> None:
        self._routes: list[Route] = []

    def add(self, method: str, pattern: str, handler: Handler) -> None:
        """Register a handler. ":name" in the pattern captures a segment."""
        self._routes.append(Route(method, pattern, handler))

    def resolve(self, method: str, raw_path: str) -> tuple[Handler | None, Any]:
        """Return (handler, request) or (None, path_matched_other_method)."""
        parsed = urlparse(raw_path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        other_method = False

        for route in self._routes:
            match = route.pattern.match(path)
            if not match:
                continue
            if route.method != method:
                other_method = True
                continue
            return route.handler, {"path": path, "query": query, "params": match.groupdict()}

        return None, other_method
