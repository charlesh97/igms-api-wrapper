from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
import json

from .client import IGMSClient


ACTIVE_BOOKING_STATUSES = {"accepted", "confirmed", "pending", "requested"}
DEFAULT_STATE_PATH = Path(".state/daily_status_state.json")


@dataclass
class MessageAlert:
    property_uid: str
    reservation_code: str | None
    booking_uid: str | None
    thread_id: int | None
    last_message_dttm: str | None
    new_message_count: int
    latest_message_preview: str | None


@dataclass
class PropertyStatus:
    property_uid: str
    property_name: str
    address: str
    active: bool
    listing_count: int
    listed_count: int
    next_checkin: dict[str, Any] | None
    next_checkout: dict[str, Any] | None
    next_7d_available: int
    next_7d_blocked: int
    next_7d_avg_price: float | None
    new_bookings: list[dict[str, Any]]
    checkouts_today: list[dict[str, Any]]
    new_message_alerts: list[MessageAlert]


@dataclass
class PortfolioStatus:
    generated_at: str
    last_run_at: str | None
    state_file: str | None
    properties: list[PropertyStatus]


# --- Internal helpers ---


def _parse_local_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _parse_iso_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except Exception:
        return None
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def _load_state(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_state(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _message_preview(text: str | None, limit: int = 80) -> str | None:
    if not text:
        return None
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1] + "\u2026"


def _serialize_message_alert(alert: MessageAlert) -> dict[str, Any]:
    return asdict(alert)


def _serialize_property_status(status: PropertyStatus) -> dict[str, Any]:
    payload = asdict(status)
    payload["new_message_alerts"] = [_serialize_message_alert(a) for a in status.new_message_alerts]
    return payload


def _booking_property_maps(
    listings: list[dict[str, Any]], bookings: list[dict[str, Any]]
) -> tuple[dict[str, str], dict[str, str]]:
    listing_to_property: dict[str, str] = {}
    booking_to_property: dict[str, str] = {}
    for listing in listings:
        listing_uid = listing.get("listing_uid")
        property_uid = listing.get("property_uid")
        if listing_uid and property_uid:
            listing_to_property[str(listing_uid)] = str(property_uid)
    for booking in bookings:
        booking_uid = booking.get("booking_uid")
        property_uid = booking.get("property_uid")
        if booking_uid and property_uid:
            booking_to_property[str(booking_uid)] = str(property_uid)
    return listing_to_property, booking_to_property


def _find_new_bookings(prop_bookings: list[dict[str, Any]], last_run_dt: datetime | None) -> list[dict[str, Any]]:
    if not last_run_dt:
        return []
    results = []
    for booking in prop_bookings:
        booked_dt = _parse_local_dt(booking.get("booked_dttm")) or _parse_local_dt(booking.get("created_dttm"))
        if booked_dt and booked_dt > last_run_dt:
            results.append(booking)
    results.sort(key=lambda row: row.get("booked_dttm") or row.get("created_dttm") or "")
    return results


def _find_checkouts_today(prop_bookings: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    results = []
    for booking in prop_bookings:
        status = str(booking.get("booking_status", ""))
        if status not in ACTIVE_BOOKING_STATUSES:
            continue
        checkout_dt = _parse_local_dt(booking.get("local_checkout_dttm"))
        if checkout_dt and checkout_dt.date() == today:
            results.append(booking)
    results.sort(key=lambda row: row.get("local_checkout_dttm") or "")
    return results


def _find_recent_threads(
    client: IGMSClient,
    *,
    listings: list[dict[str, Any]],
    bookings: list[dict[str, Any]],
    last_run_dt: datetime | None,
    today: date,
) -> dict[str, list[MessageAlert]]:
    if not last_run_dt:
        return {}

    filters = {
        "fromDate": last_run_dt.date().isoformat(),
        "toDate": today.isoformat(),
    }
    threads = client.get_all_threads(**filters)
    listing_to_property, booking_to_property = _booking_property_maps(listings, bookings)
    grouped: dict[str, list[MessageAlert]] = {}

    for thread in threads:
        last_message_raw = thread.get("lastMessageDttm") or thread.get("updateDttm")
        last_message_dt = _parse_local_dt(last_message_raw)
        if not last_message_dt or last_message_dt <= last_run_dt:
            continue

        booking_uid = thread.get("bookingUid")
        listing_uid = thread.get("listingUid")
        property_uid = None
        if booking_uid:
            property_uid = booking_to_property.get(str(booking_uid))
        if property_uid is None and listing_uid:
            property_uid = listing_to_property.get(str(listing_uid))
        if property_uid is None:
            continue

        messages = thread.get("messages") if isinstance(thread.get("messages"), list) else []
        new_messages = [
            m for m in messages
            if (message_dt := _parse_local_dt(m.get("messageDttm"))) and message_dt > last_run_dt
        ]
        latest_message = new_messages[-1] if new_messages else (messages[-1] if messages else None)
        grouped.setdefault(property_uid, []).append(
            MessageAlert(
                property_uid=property_uid,
                reservation_code=thread.get("reservationCode"),
                booking_uid=booking_uid,
                thread_id=thread.get("threadId"),
                last_message_dttm=last_message_raw,
                new_message_count=len(new_messages),
                latest_message_preview=_message_preview((latest_message or {}).get("messageText")),
            )
        )

    for alerts in grouped.values():
        alerts.sort(key=lambda item: item.last_message_dttm or "")
    return grouped


# --- Public API ---


def build_portfolio_status(
    client: IGMSClient,
    *,
    today: date | None = None,
    days: int = 7,
    state_file: str | Path | None = DEFAULT_STATE_PATH,
    write_state: bool = True,
) -> PortfolioStatus:
    """Build a portfolio-wide status summary across all properties."""
    today = today or date.today()
    end = today + timedelta(days=days - 1)
    state_path = Path(state_file) if state_file else None
    previous_state = _load_state(state_path)
    last_run_at = previous_state.get("last_run_at") if isinstance(previous_state, dict) else None
    last_run_dt = _parse_iso_dt(last_run_at)

    properties = client.get_all_properties()
    listings = client.get_all_listings()
    bookings = client.get_all_bookings()
    recent_threads_by_property = _find_recent_threads(
        client,
        listings=listings,
        bookings=bookings,
        last_run_dt=last_run_dt,
        today=today,
    )

    statuses: list[PropertyStatus] = []

    for prop in properties:
        property_uid = str(prop.get("property_uid", ""))
        property_name = str(prop.get("name", ""))
        prop_listings = [row for row in listings if row.get("property_uid") == property_uid]
        prop_bookings = [row for row in bookings if row.get("property_uid") == property_uid]

        future_checkins = []
        future_checkouts = []
        for booking in prop_bookings:
            status = str(booking.get("booking_status", ""))
            if status not in ACTIVE_BOOKING_STATUSES:
                continue
            checkin_dt = _parse_local_dt(booking.get("local_checkin_dttm"))
            checkout_dt = _parse_local_dt(booking.get("local_checkout_dttm"))
            if checkin_dt and checkin_dt.date() >= today:
                future_checkins.append((checkin_dt, booking))
            if checkout_dt and checkout_dt.date() >= today:
                future_checkouts.append((checkout_dt, booking))

        future_checkins.sort(key=lambda item: item[0])
        future_checkouts.sort(key=lambda item: item[0])

        calendar = client.get_calendar(property_uid, today.isoformat(), end.isoformat()).get("data", [])
        available = sum(1 for row in calendar if row.get("is_available") == 1)
        blocked = len(calendar) - available
        prices = [row.get("price") for row in calendar if isinstance(row.get("price"), (int, float))]
        avg_price = round(sum(prices) / len(prices), 2) if prices else None

        statuses.append(
            PropertyStatus(
                property_uid=property_uid,
                property_name=property_name,
                address=str(prop.get("address", "")),
                active=bool(prop.get("is_active")),
                listing_count=len(prop_listings),
                listed_count=sum(1 for row in prop_listings if row.get("listing_status") == "listed"),
                next_checkin=future_checkins[0][1] if future_checkins else None,
                next_checkout=future_checkouts[0][1] if future_checkouts else None,
                next_7d_available=available,
                next_7d_blocked=blocked,
                next_7d_avg_price=avg_price,
                new_bookings=_find_new_bookings(prop_bookings, last_run_dt),
                checkouts_today=_find_checkouts_today(prop_bookings, today),
                new_message_alerts=recent_threads_by_property.get(property_uid, []),
            )
        )

    generated_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    status = PortfolioStatus(
        generated_at=generated_at,
        last_run_at=last_run_at,
        state_file=str(state_path) if state_path else None,
        properties=statuses,
    )

    if write_state:
        _save_state(
            state_path,
            {
                "last_run_at": generated_at,
                "property_count": len(statuses),
            },
        )

    return status


def portfolio_status_to_dict(status: PortfolioStatus) -> dict[str, Any]:
    """Serialize a PortfolioStatus to a plain dict."""
    return {
        "generated_at": status.generated_at,
        "last_run_at": status.last_run_at,
        "state_file": status.state_file,
        "properties": [_serialize_property_status(item) for item in status.properties],
    }


def format_portfolio_status_text(status: PortfolioStatus) -> str:
    """Format a PortfolioStatus as a human-readable text report."""
    lines = [f"iGMS portfolio status \u2014 generated {status.generated_at}"]
    if status.last_run_at:
        lines.append(f"Since last run: {status.last_run_at}")
    else:
        lines.append("Since last run: baseline run (no prior state yet)")

    total_new_bookings = sum(len(p.new_bookings) for p in status.properties)
    total_checkouts = sum(len(p.checkouts_today) for p in status.properties)
    total_messages = sum(len(p.new_message_alerts) for p in status.properties)
    lines.append(
        f"Overall: {total_new_bookings} new bookings, {total_checkouts} checkouts today, {total_messages} message threads needing review"
    )

    for prop in status.properties:
        lines.append("")
        lines.append(f"{prop.property_name} ({prop.property_uid})")
        lines.append(f"- Address: {prop.address}")
        lines.append(f"- Active: {'yes' if prop.active else 'no'} | Listings listed: {prop.listed_count}/{prop.listing_count}")

        if prop.new_bookings:
            lines.append(f"- New bookings since last run: {len(prop.new_bookings)}")
            for b in prop.new_bookings[:3]:
                lines.append(
                    f"  - {b.get('reservation_code')} | {b.get('platform_type')} | booked {b.get('booked_dttm') or b.get('created_dttm')} | {b.get('local_checkin_dttm')} \u2192 {b.get('local_checkout_dttm')}"
                )
        else:
            lines.append("- New bookings since last run: none")

        if prop.checkouts_today:
            lines.append(f"- Checkouts today: {len(prop.checkouts_today)}")
            for b in prop.checkouts_today[:3]:
                lines.append(
                    f"  - {b.get('reservation_code')} | {b.get('platform_type')} | checkout {b.get('local_checkout_dttm')}"
                )
        else:
            lines.append("- Checkouts today: none")

        if prop.new_message_alerts:
            lines.append(f"- New messages to review: {len(prop.new_message_alerts)}")
            for alert in prop.new_message_alerts[:3]:
                preview = f" | {alert.latest_message_preview}" if alert.latest_message_preview else ""
                lines.append(
                    f"  - {alert.reservation_code or alert.booking_uid or alert.thread_id} | last message {alert.last_message_dttm} | {alert.new_message_count} new{preview}"
                )
        else:
            lines.append("- New messages to review: none")

        if prop.next_checkin:
            lines.append(
                f"- Next check-in: {prop.next_checkin.get('local_checkin_dttm')} "
                f"[{prop.next_checkin.get('reservation_code')} | {prop.next_checkin.get('platform_type')} | {prop.next_checkin.get('booking_status')}]"
            )
        else:
            lines.append("- Next check-in: none on file")
        if prop.next_checkout:
            lines.append(
                f"- Next check-out: {prop.next_checkout.get('local_checkout_dttm')} "
                f"[{prop.next_checkout.get('reservation_code')} | {prop.next_checkout.get('platform_type')} | {prop.next_checkout.get('booking_status')}]"
            )
        else:
            lines.append("- Next check-out: none on file")
        avg = f"${prop.next_7d_avg_price}" if prop.next_7d_avg_price is not None else "n/a"
        lines.append(
            f"- Next 7 days: {prop.next_7d_available} available / {prop.next_7d_blocked} blocked | avg nightly price {avg}"
        )
    return "\n".join(lines)
