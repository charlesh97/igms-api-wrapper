from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterator
import secrets
import urllib.parse

import requests

from .config import IGMSConfig


def generate_secret(length_bytes: int = 48) -> str:
    """Generate a cryptographically random URL-safe secret."""
    return secrets.token_urlsafe(length_bytes)


def build_auth_url(config: IGMSConfig, state: str | None = None) -> str:
    """Build the iGMS OAuth authorization URL."""
    if not config.client_id:
        raise ValueError("Missing IGMS_CLIENT_ID")
    if not config.redirect_uri:
        raise ValueError("Missing IGMS_REDIRECT_URI")

    params = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "scope": config.scope,
        "state": state or secrets.token_urlsafe(24),
    }
    return f"{config.auth_url}?{urllib.parse.urlencode(params)}"


def exchange_code(
    code: str,
    config: IGMSConfig,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Exchange an OAuth authorization code for an access token."""
    if not config.client_id:
        raise ValueError("Missing IGMS_CLIENT_ID")
    if not config.redirect_uri:
        raise ValueError("Missing IGMS_REDIRECT_URI")

    params = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.redirect_uri,
        "client_id": config.client_id,
    }
    if config.client_secret:
        params["client_secret"] = config.client_secret

    http = session or requests.Session()
    response = http.get(config.token_url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def normalize_human_name(value: str) -> str:
    """Normalize a property/listing name for fuzzy matching."""
    chars = []
    last_was_space = False
    for char in value.casefold():
        if char.isalnum():
            chars.append(char)
            last_was_space = False
            continue
        if not last_was_space:
            chars.append(" ")
            last_was_space = True
    return "".join(chars).strip()


def _response_meta(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    meta = payload.get("meta")
    return meta if isinstance(meta, dict) else {}


class IGMSAPIError(Exception):
    """Raised when iGMS returns a top-level error payload (even with HTTP 200)."""


def _raise_on_error_payload(payload: Any) -> None:
    """iGMS can return HTTP 200 with a top-level `error` body (documented quirk).

    Treat that as a hard failure instead of silently yielding zero records —
    a silent empty result would let the message review print wakeAgent=false
    and skip an entire day of guest messages.
    """
    if isinstance(payload, dict) and "error" in payload and "data" not in payload:
        error = payload["error"]
        if isinstance(error, dict):
            message = error.get("message") or error.get("error") or str(error)
        else:
            message = str(error)
        raise IGMSAPIError("iGMS API error: {}".format(message))


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    """Extract record list from an API response payload."""
    _raise_on_error_payload(payload)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("data", "results", "items", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    list_values = [value for value in payload.values() if isinstance(value, list)]
    if len(list_values) == 1:
        return [item for item in list_values[0] if isinstance(item, dict)]
    return []


def _has_next_page(payload: Any, page: int, record_count: int) -> bool:
    """Determine if there are more pages of results."""
    meta = _response_meta(payload)
    explicit = meta.get("has_next_page")
    if explicit is None:
        explicit = meta.get("hasNextPage")
    if explicit is not None:
        return _coerce_meta_flag(explicit)

    next_page = meta.get("next_page")
    if next_page is None:
        next_page = meta.get("nextPage")
    if next_page is not None:
        return _coerce_meta_flag(next_page)

    meta_page = meta.get("page")
    if isinstance(meta_page, int) and meta_page > page:
        return True

    total_pages = meta.get("total_pages") or meta.get("totalPages")
    if isinstance(total_pages, int):
        return page < total_pages

    return record_count > 0


def _coerce_meta_flag(value: Any) -> bool:
    """Coerce common API pagination flag shapes to a boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"", "0", "false", "f", "no", "n", "none", "null"}:
            return False
        if normalized in {"1", "true", "t", "yes", "y"}:
            return True
    return bool(value)


@dataclass
class APIResponse:
    """Response from an iGMS API call."""

    status_code: int
    payload: Any
    url: str


class IGMSClient:
    """Client for the iGMS property management API."""

    def __init__(
        self,
        config: IGMSConfig | None = None,
        *,
        access_token: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.config = config or IGMSConfig.from_env()
        self.session = session or requests.Session()
        self.access_token = access_token or self.config.access_token

    @classmethod
    def from_env(cls) -> IGMSClient:
        """Create a client configured from environment variables."""
        return cls(config=IGMSConfig.from_env())

    def require_access_token(self) -> str:
        if not self.access_token:
            raise ValueError("Missing IGMS_ACCESS_TOKEN. Set IGMS_ACCESS_TOKEN env var or pass access_token= to the constructor.")
        return self.access_token

    def request(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        method: str = "GET",
        json_body: dict[str, Any] | None = None,
    ) -> APIResponse:
        """Make an authenticated request to the iGMS API."""
        query = dict(params or {})
        query["access_token"] = self.require_access_token()
        url = urllib.parse.urljoin(self.config.api_base, path)
        response = self.session.request(
            method.upper(),
            url,
            params=query,
            json=json_body,
            timeout=30,
        )
        try:
            payload = response.json()
        except Exception:
            payload = response.text
        response.raise_for_status()
        return APIResponse(status_code=response.status_code, payload=payload, url=response.url)

    # --- Core endpoints ---

    def get_properties(self, page: int = 1) -> Any:
        return self.request("/api/v1/property", params={"page": page}).payload

    def get_property(self, property_uid: str) -> Any:
        """Get one property by its iGMS property UID.

        This endpoint must not be called with a channel/listing UID.  If iGMS
        has merged the property, its error payload includes ``newPropertyUid``
        so callers can re-sync their inventory.
        """
        return self.request(f"/api/v1/property/{property_uid}").payload

    def get_listings(self, page: int = 1, **filters: Any) -> Any:
        """List channel listings, optionally filtered by documented fields."""
        params = {"page": page, **filters}
        return self.request("/api/v1/listings", params=params).payload

    def get_bookings(self, page: int = 1, **filters: Any) -> Any:
        params = {"page": page, **filters}
        return self.request("/api/v1/bookings", params=params).payload

    def get_calendar(self, property_uid: str, from_date: str, to_date: str) -> Any:
        params = {
            "property_uid": property_uid,
            "from_date": from_date,
            "to_date": to_date,
        }
        return self.request("/api/v1/get-calendar-data", params=params).payload

    def get_request_status(self, request_uid: str | int) -> Any:
        """Return the asynchronous status of a calendar/listing write."""
        return self.request(
            "/api/v1/get-request-status",
            params={"request_uid": request_uid},
        ).payload

    def get_threads(self, page: int = 1, **filters: Any) -> Any:
        params = {"page": page, **filters}
        return self.request("/api/v1/get-threads", params=params).payload

    def message_booking_guest(
        self,
        message: str,
        *,
        thread_id: str | None = None,
        booking_uid: str | None = None,
        channel: str | None = None,
    ) -> Any:
        """Send a message to the main guest of a booking.

        Args:
            message: The message text. Length may be limited for certain channel types.
            thread_id: Thread ID. Required unless booking_uid is provided.
            booking_uid: UID of a booking. Required unless thread_id is provided.
            channel: Channel type — 'email' for direct bookings, 'platform' for
                other platforms (default).

        Returns the API payload, which typically includes the sent message UID
        (usable with get_message_status).
        """
        if not thread_id and not booking_uid:
            raise ValueError("Provide either thread_id or booking_uid to send a message")
        if not message.strip():
            raise ValueError("message must not be empty")

        body: dict[str, Any] = {"message": message}
        if thread_id:
            body["thread_id"] = thread_id
        if booking_uid:
            body["booking_uid"] = booking_uid
        if channel:
            body["channel"] = channel

        return self.request(
            "/api/v1/message-booking-guest",
            method="POST",
            json_body=body,
        ).payload

    def get_message_status(self, message_uid: str) -> Any:
        """Get the delivery status of a message sent via message_booking_guest.

        Args:
            message_uid: UID of the message (returned by message_booking_guest).
        """
        return self.request(
            "/api/v1/message-status",
            params={"message_uid": message_uid},
        ).payload

    # --- Pagination helpers ---

    def iter_paginated(
        self,
        fetch_page: Callable[..., Any],
        *,
        start_page: int = 1,
        **kwargs: Any,
    ) -> Iterator[dict[str, Any]]:
        """Iterate through all pages of a paginated endpoint."""
        page = start_page
        while True:
            payload = fetch_page(page=page, **kwargs)
            records = _records_from_payload(payload)
            for record in records:
                yield record
            if not _has_next_page(payload, page, len(records)):
                break
            page += 1

    def collect_paginated(
        self,
        fetch_page: Callable[..., Any],
        *,
        start_page: int = 1,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Collect all records from a paginated endpoint into a list."""
        return list(self.iter_paginated(fetch_page, start_page=start_page, **kwargs))

    # --- Convenience: fetch all ---

    def get_all_properties(self, start_page: int = 1) -> list[dict[str, Any]]:
        return self.collect_paginated(self.get_properties, start_page=start_page)

    def get_all_listings(self, start_page: int = 1, **filters: Any) -> list[dict[str, Any]]:
        return self.collect_paginated(
            self.get_listings,
            start_page=start_page,
            **filters,
        )

    def get_all_bookings(self, start_page: int = 1, **filters: Any) -> list[dict[str, Any]]:
        return self.collect_paginated(self.get_bookings, start_page=start_page, **filters)

    def get_all_threads(self, start_page: int = 1, **filters: Any) -> list[dict[str, Any]]:
        return self.collect_paginated(self.get_threads, start_page=start_page, **filters)

    # --- Name lookup helpers ---

    def find_property_by_name(
        self,
        name: str,
        *,
        properties: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Find a property by fuzzy name match."""
        return _find_by_name(
            properties if properties is not None else self.get_all_properties(),
            name,
            keys=("name", "property_name", "address"),
        )

    def find_listing_by_name(
        self,
        name: str,
        *,
        listings: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Find a listing by fuzzy name match."""
        return _find_by_name(
            listings if listings is not None else self.get_all_listings(),
            name,
            keys=("listing_name", "property_name", "name"),
        )


def _find_by_name(
    items: list[dict[str, Any]],
    target_name: str,
    *,
    keys: tuple[str, ...],
) -> dict[str, Any] | None:
    normalized_target = normalize_human_name(target_name)
    fallback: dict[str, Any] | None = None

    for item in items:
        candidates = [
            normalize_human_name(str(item.get(key, "")))
            for key in keys
            if item.get(key)
        ]
        if normalized_target in candidates:
            return item
        if any(normalized_target and normalized_target in c for c in candidates):
            fallback = fallback or item

    return fallback
