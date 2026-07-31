from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import requests

from .client import IGMSClient, build_auth_url, exchange_code, generate_secret
from .config import IGMSConfig
from .reports import build_portfolio_status, format_portfolio_status_text, portfolio_status_to_dict


def _json_arg(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object")
    return parsed


def _print_payload(payload: Any) -> None:
    if isinstance(payload, str):
        print(payload)
        return
    print(json.dumps(payload, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="igms", description="iGMS property management API wrapper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # Auth helpers
    sub.add_parser("generate-secret", help="Generate a random OAuth state value")
    sub.add_parser("auth-url", help="Print the OAuth authorization URL")

    p_exchange = sub.add_parser("exchange", help="Exchange an auth code for an access token")
    p_exchange.add_argument("--code", required=True)

    # Raw API access
    p_api = sub.add_parser("api", help="Make a raw API call")
    p_api.add_argument("--path", required=True, help="API path, e.g. /api/v1/listings")
    p_api.add_argument("--method", default="GET")
    p_api.add_argument("--params", help='JSON object, e.g. {"page":1}')
    p_api.add_argument("--body", help="JSON object for POST body")

    # Resource endpoints
    p_properties = sub.add_parser("properties", help="List properties")
    p_properties.add_argument("--page", type=int, default=1)

    p_listings = sub.add_parser("listings", help="List listings")
    p_listings.add_argument("--page", type=int, default=1)

    p_bookings = sub.add_parser("bookings", help="List bookings")
    p_bookings.add_argument("--page", type=int, default=1)
    p_bookings.add_argument("--filters", help='JSON filter object, e.g. {"booking_status":"accepted"}')

    p_calendar = sub.add_parser("calendar", help="Get calendar data for a property")
    p_calendar.add_argument("--property-uid", required=True)
    p_calendar.add_argument("--from-date", required=True)
    p_calendar.add_argument("--to-date", required=True)

    p_threads = sub.add_parser("threads", help="List message threads")
    p_threads.add_argument("--page", type=int, default=1)
    p_threads.add_argument("--filters", help='JSON filter object, e.g. {"bookingsUids":"abc"}')

    p_send = sub.add_parser("send-message", help="Send a message to a booking's main guest")
    p_send.add_argument("--message", required=True, help="Message text")
    p_send.add_argument("--thread-id", help="Thread ID (required unless --booking-uid given)")
    p_send.add_argument("--booking-uid", help="Booking UID (required unless --thread-id given)")
    p_send.add_argument("--channel", help="Channel: 'email' for direct bookings, 'platform' otherwise")

    p_msg_status = sub.add_parser("message-status", help="Get status of a sent message")
    p_msg_status.add_argument("--message-uid", required=True, help="UID returned by send-message")

    # Name lookup
    p_find_property = sub.add_parser("find-property", help="Find a property by name")
    p_find_property.add_argument("name")

    p_find_listing = sub.add_parser("find-listing", help="Find a listing by name")
    p_find_listing.add_argument("name")

    # Portfolio status
    p_status = sub.add_parser("status", help="Portfolio status summary")
    p_status.add_argument("--days", type=int, default=7)
    p_status.add_argument("--json", action="store_true", dest="as_json")
    p_status.add_argument("--state-file")
    p_status.add_argument("--no-write-state", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        config = IGMSConfig.from_env()

        if args.cmd == "generate-secret":
            print(generate_secret())
            return 0

        if args.cmd == "auth-url":
            print(build_auth_url(config))
            return 0

        if args.cmd == "exchange":
            _print_payload(exchange_code(args.code, config))
            return 0

        client = IGMSClient(config=config)

        if args.cmd == "properties":
            _print_payload(client.get_properties(page=args.page))
            return 0

        if args.cmd == "listings":
            _print_payload(client.get_listings(page=args.page))
            return 0

        if args.cmd == "bookings":
            _print_payload(client.get_bookings(page=args.page, **_json_arg(args.filters)))
            return 0

        if args.cmd == "calendar":
            _print_payload(client.get_calendar(args.property_uid, args.from_date, args.to_date))
            return 0

        if args.cmd == "threads":
            _print_payload(client.get_threads(page=args.page, **_json_arg(args.filters)))
            return 0

        if args.cmd == "send-message":
            _print_payload(
                client.message_booking_guest(
                    args.message,
                    thread_id=args.thread_id,
                    booking_uid=args.booking_uid,
                    channel=args.channel,
                )
            )
            return 0

        if args.cmd == "message-status":
            _print_payload(client.get_message_status(args.message_uid))
            return 0

        if args.cmd == "find-property":
            _print_payload(client.find_property_by_name(args.name))
            return 0

        if args.cmd == "find-listing":
            _print_payload(client.find_listing_by_name(args.name))
            return 0

        if args.cmd == "api":
            response = client.request(
                args.path,
                method=args.method,
                params=_json_arg(args.params),
                json_body=_json_arg(args.body) if args.body else None,
            )
            print(f"URL: {response.url}")
            print(f"HTTP {response.status_code}")
            _print_payload(response.payload)
            return 0

        if args.cmd == "status":
            status = build_portfolio_status(
                client,
                days=args.days,
                state_file=args.state_file,
                write_state=not args.no_write_state,
            )
            if args.as_json:
                _print_payload(portfolio_status_to_dict(status))
            else:
                print(format_portfolio_status_text(status))
            return 0

        parser.print_help(sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except requests.RequestException as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1
