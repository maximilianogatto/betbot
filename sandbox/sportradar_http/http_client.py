"""Pure HTTP replay client for Statshub `/gismo/` endpoints.

Purpose:
    Use a previously bootstrapped `SportradarSessionState` to call signed
    Sportradar/Statshub endpoints without keeping Playwright open.

How it connects:
    - Receives token/headers/cookies from `session_manager`.
    - Builds signed URLs for named endpoint paths.
    - Is consumed by `endpoints/*` wrappers and pipeline scripts.

Key behavior:
    - validates blocked/expired/empty/invalid-json responses;
    - retries transient failures;
    - optionally refreshes the session through `SportradarSessionManager`;
    - records request metrics and endpoint timings.

Data contract:
    Public methods return raw gismo JSON dictionaries. Normalization is handled
    later by `normalizers.py` so this client stays transport-focused.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import logging
import time
from typing import Any, Protocol
from urllib.parse import urlparse, urlunparse

import httpx

from sandbox.sportradar_http.session_manager import (
    DEFAULT_ORIGIN,
    DEFAULT_REFERER,
    SportradarSessionManager,
    SportradarSessionState,
    build_replay_headers,
    extract_gismo_endpoint_key,
    is_blocked_payload,
    is_expired_payload,
    safe_json_loads,
)


logger = logging.getLogger(__name__)
DEFAULT_GISMO_HOST = "sh.fn.sportradar.com"


class RefreshableSessionManager(Protocol):
    state: SportradarSessionState | None

    def refresh_session(self) -> SportradarSessionState:
        ...


@dataclass(slots=True)
class ResponseValidation:
    """Result of checking one HTTP response for replay usability."""

    ok: bool
    status_code: int | None
    endpoint_key: str | None
    blocked: bool = False
    expired: bool = False
    empty: bool = False
    invalid_json: bool = False
    http_error: bool = False
    reason: str | None = None


@dataclass(slots=True)
class RequestMetrics:
    """Mutable counters and timing buckets for HTTP replay calls."""

    total_requests: int = 0
    success_count: int = 0
    retry_count: int = 0
    refresh_count: int = 0
    blocked_count: int = 0
    expired_count: int = 0
    empty_count: int = 0
    invalid_json_count: int = 0
    http_error_count: int = 0
    endpoint_timings_ms: dict[str, list[float]] = field(default_factory=dict)

    def record(self, endpoint_key: str | None, elapsed_ms: float, validation: ResponseValidation) -> None:
        self.total_requests += 1
        endpoint = endpoint_key or "unknown"
        self.endpoint_timings_ms.setdefault(endpoint, []).append(round(elapsed_ms, 2))
        self.success_count += int(validation.ok)
        self.blocked_count += int(validation.blocked)
        self.expired_count += int(validation.expired)
        self.empty_count += int(validation.empty)
        self.invalid_json_count += int(validation.invalid_json)
        self.http_error_count += int(validation.http_error)

    def summary(self) -> dict[str, Any]:
        timing_summary: dict[str, dict[str, float | int]] = {}
        for endpoint, values in self.endpoint_timings_ms.items():
            timing_summary[endpoint] = {
                "count": len(values),
                "min_ms": min(values),
                "max_ms": max(values),
                "avg_ms": round(sum(values) / len(values), 2),
            }
        payload = asdict(self)
        payload["endpoint_timing_summary"] = timing_summary
        return payload


class SportradarHTTPError(RuntimeError):
    """Raised when a replay request cannot produce a valid payload."""

    def __init__(self, message: str, *, validation: ResponseValidation, url: str) -> None:
        super().__init__(message)
        self.validation = validation
        self.url = url


class SportradarHTTPClient:
    """HTTP replay client for already-bootstrapped Statshub/Sportradar sessions.

    This class does not import or manage Playwright. Optional refresh is
    delegated to `SportradarSessionManager`, keeping browser bootstrap separate
    from HTTP replay.
    """

    def __init__(
        self,
        *,
        session_state: SportradarSessionState | None = None,
        session_manager: RefreshableSessionManager | None = None,
        auto_refresh: bool = True,
        retries: int = 2,
        timeout_seconds: float = 20.0,
        debug: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.session_manager = session_manager
        self.state = session_state or (session_manager.state if session_manager else None)
        self.auto_refresh = auto_refresh
        self.retries = max(0, retries)
        self.timeout_seconds = timeout_seconds
        self.debug = debug
        self.metrics = RequestMetrics()
        self._transport = transport

    @classmethod
    def with_bootstrap(
        cls,
        manager: SportradarSessionManager,
        *,
        retries: int = 2,
        timeout_seconds: float = 20.0,
        debug: bool = False,
    ) -> "SportradarHTTPClient":
        state = manager.state or manager.refresh_session()
        return cls(
            session_state=state,
            session_manager=manager,
            retries=retries,
            timeout_seconds=timeout_seconds,
            debug=debug,
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        expect_json: bool = True,
        allow_refresh: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute one HTTP request with validation, retry, and optional refresh.

        Args:
            method: HTTP method, usually `GET`.
            url: Fully signed URL. Use `get_gismo()` for endpoint-name based calls.
            expect_json: When true, non-JSON payloads fail validation.
            allow_refresh: When true, blocked/expired payloads may trigger a
                session refresh if a session manager exists.
            **kwargs: Passed directly to `httpx.Client.request`.

        Returns:
            The validated `httpx.Response`.
        """

        self.maybe_refresh_session()
        last_error: SportradarHTTPError | None = None
        attempts = self.retries + 1 + int(self.auto_refresh and allow_refresh)
        refreshes_for_request = 0
        for attempt_index in range(attempts):
            response, validation = self._request_once(method, url, expect_json=expect_json, **kwargs)
            if validation.ok:
                return response
            if self._should_refresh(validation, allow_refresh=allow_refresh) and refreshes_for_request < 1:
                refreshes_for_request += 1
                self.metrics.refresh_count += 1
                self.refresh_session()
                url = self.refresh_signed_url(url)
                continue
            if attempt_index < attempts - 1 and self._should_retry(validation):
                self.metrics.retry_count += 1
                continue
            last_error = SportradarHTTPError(
                f"Sportradar HTTP request failed: {validation.reason}",
                validation=validation,
                url=url,
            )
            break
        assert last_error is not None
        raise last_error

    def request_json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        """Execute a request and return a JSON object payload."""

        response = self.request(method, url, expect_json=True, **kwargs)
        payload = safe_json_loads(response.text)
        if not isinstance(payload, dict):
            validation = self.validate_response(response, expect_json=True)
            raise SportradarHTTPError("Sportradar response did not contain a JSON object.", validation=validation, url=url)
        return payload

    def get_gismo(
        self,
        endpoint_path: str,
        *,
        namespace: str = "bet365",
        language: str = "en",
        timezone: str = "Etc:UTC",
        host: str = DEFAULT_GISMO_HOST,
    ) -> dict[str, Any]:
        """Call a `/gismo/<endpoint_path>` endpoint using the current signed token.

        Args:
            endpoint_path: Endpoint path without `/gismo/`, for example
                `match_markets/61624678`.
            namespace: Usually `bet365`; some endpoints use `common`.
            language: Statshub language segment.
            timezone: Statshub timezone segment, for example `Etc:UTC`.
            host: Gismo host, normally `sh.fn.sportradar.com`.
        """

        url = self.build_gismo_url(
            endpoint_path,
            namespace=namespace,
            language=language,
            timezone=timezone,
            host=host,
        )
        return self.request_json("GET", url)

    def validate_response(self, response: httpx.Response, *, expect_json: bool = True) -> ResponseValidation:
        """Classify a response as usable, blocked, expired, empty, or invalid."""

        body = response.text
        body_json = safe_json_loads(body)
        endpoint_key = extract_gismo_endpoint_key(str(response.url))
        http_error = response.status_code >= 400
        empty = len(body.strip()) == 0
        invalid_json = expect_json and not empty and body_json is None
        blocked = is_blocked_payload(body_json, body)
        expired = is_expired_payload(body_json, body)
        ok = not any((http_error, empty, invalid_json, blocked, expired))
        reason = None
        if http_error:
            reason = f"http_error:{response.status_code}"
        elif expired:
            reason = "token_expired"
        elif blocked:
            reason = "blocked_payload"
        elif empty:
            reason = "empty_payload"
        elif invalid_json:
            reason = "invalid_json"
        return ResponseValidation(
            ok=ok,
            status_code=response.status_code,
            endpoint_key=endpoint_key,
            blocked=blocked,
            expired=expired,
            empty=empty,
            invalid_json=invalid_json,
            http_error=http_error,
            reason=reason,
        )

    def maybe_refresh_session(self) -> None:
        if self.state is not None and self.state.signed_token is not None and not self.state.signed_token.is_expired():
            return
        if not self.auto_refresh:
            return
        self.refresh_session()

    def refresh_session(self) -> SportradarSessionState:
        if self.session_manager is None:
            raise SportradarHTTPError(
                "No session manager available for refresh.",
                validation=ResponseValidation(False, None, None, reason="refresh_unavailable"),
                url="",
            )
        self.state = self.session_manager.refresh_session()
        logger.info("Sportradar HTTP session refreshed token_expiration=%s", self.state.token_expiration())
        return self.state

    def refresh_signed_url(self, url: str) -> str:
        """Replace the `T` query value in an existing gismo URL with the current token."""

        if self.state is None or self.state.signed_token is None:
            return url
        parsed = urlparse(url)
        query = f"T={self.state.signed_token.raw}"
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment))

    def build_gismo_url(
        self,
        endpoint_path: str,
        *,
        namespace: str = "bet365",
        language: str = "en",
        timezone: str = "Etc:UTC",
        host: str = DEFAULT_GISMO_HOST,
    ) -> str:
        """Construct a signed gismo URL from an endpoint path and current token."""

        if self.state is None or self.state.signed_token is None:
            if self.auto_refresh:
                self.refresh_session()
            else:
                raise ValueError("Cannot build gismo URL without a signed token.")
        assert self.state is not None and self.state.signed_token is not None
        clean_path = "/".join(str(part).strip("/") for part in endpoint_path.split("/") if str(part).strip("/"))
        return f"https://{host}/{namespace}/{language}/{timezone}/gismo/{clean_path}?T={self.state.signed_token.raw}"

    def _request_once(
        self,
        method: str,
        url: str,
        *,
        expect_json: bool,
        **kwargs: Any,
    ) -> tuple[httpx.Response, ResponseValidation]:
        headers = {**build_replay_headers(), **((self.state.replay_headers if self.state else {}) or {})}
        cookies = (self.state.cookies if self.state else {}) or {}
        started = time.monotonic()
        with httpx.Client(
            headers=headers,
            cookies=cookies,
            timeout=self.timeout_seconds,
            follow_redirects=True,
            transport=self._transport,
        ) as client:
            response = client.request(method.upper(), url, **kwargs)
        elapsed_ms = (time.monotonic() - started) * 1000
        validation = self.validate_response(response, expect_json=expect_json)
        endpoint = validation.endpoint_key or extract_gismo_endpoint_key(url)
        self.metrics.record(endpoint, elapsed_ms, validation)
        if self.debug:
            logger.info(
                "Sportradar HTTP %s %s status=%s ok=%s reason=%s elapsed_ms=%.2f",
                method.upper(),
                endpoint or url,
                response.status_code,
                validation.ok,
                validation.reason,
                elapsed_ms,
            )
        return response, validation

    @staticmethod
    def _should_retry(validation: ResponseValidation) -> bool:
        return validation.http_error or validation.empty or validation.invalid_json

    def _should_refresh(self, validation: ResponseValidation, *, allow_refresh: bool) -> bool:
        return bool(self.auto_refresh and allow_refresh and (validation.blocked or validation.expired))

    def metrics_json(self) -> dict[str, Any]:
        """Return request counters and endpoint timing summary as JSON-safe dict."""

        return self.metrics.summary()


def summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a compact structural summary of a raw gismo payload."""

    doc = payload.get("doc")
    first = doc[0] if isinstance(doc, list) and doc and isinstance(doc[0], dict) else {}
    data = first.get("data") if isinstance(first, dict) else None
    data_counts = {
        key: len(value)
        for key, value in data.items()
        if isinstance(data, dict) and isinstance(value, (list, dict))
    } if isinstance(data, dict) else None
    return {
        "queryUrl": payload.get("queryUrl"),
        "doc_event": first.get("event") if isinstance(first, dict) else None,
        "top_level_keys": sorted(payload.keys()),
        "data_type": type(data).__name__,
        "data_keys": sorted(data.keys())[:25] if isinstance(data, dict) else None,
        "data_counts": data_counts,
    }


def write_json(path: str, payload: object) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
