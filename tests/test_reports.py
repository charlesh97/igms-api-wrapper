from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from igms_wrapper.reports import build_portfolio_status, format_portfolio_status_text, portfolio_status_to_dict


class FakeClient:
    def get_all_properties(self):
        return [
            {
                "property_uid": "p1",
                "name": "Frosty Pines Cabin: 2br Retreat",
                "address": "10042 Rusty Lane",
                "is_active": 1,
            }
        ]

    def get_all_listings(self):
        return [
            {"property_uid": "p1", "listing_uid": "l1", "listing_status": "listed"},
            {"property_uid": "p1", "listing_uid": "l2", "listing_status": "unlisted"},
        ]

    def get_all_bookings(self):
        return [
            {
                "property_uid": "p1",
                "booking_uid": "b1",
                "booking_status": "accepted",
                "reservation_code": "ABC123",
                "platform_type": "airbnb",
                "booked_dttm": "2026-04-26 09:00:00",
                "local_checkin_dttm": "2026-04-28 15:00:00",
                "local_checkout_dttm": "2026-05-01 11:00:00",
            },
            {
                "property_uid": "p1",
                "booking_uid": "b2",
                "booking_status": "accepted",
                "reservation_code": "XYZ999",
                "platform_type": "vrbo",
                "booked_dttm": "2026-04-20 09:00:00",
                "local_checkin_dttm": "2026-04-24 15:00:00",
                "local_checkout_dttm": "2026-04-26 11:00:00",
            },
        ]

    def get_all_threads(self, **filters):
        return [
            {
                "threadId": 101,
                "bookingUid": "b1",
                "listingUid": "l1",
                "reservationCode": "ABC123",
                "lastMessageDttm": "2026-04-26 10:30:00",
                "messages": [
                    {"messageDttm": "2026-04-26 10:30:00", "messageText": "Can I check in early?"}
                ],
            }
        ]

    def get_calendar(self, property_uid, from_date, to_date):
        return {
            "data": [
                {"is_available": 1, "price": 200},
                {"is_available": 0, "price": 250},
                {"is_available": 1, "price": 300},
            ]
        }


class ReportTests(unittest.TestCase):
    def test_build_portfolio_status_baseline(self):
        status = build_portfolio_status(FakeClient(), today=date(2026, 4, 26), days=3, state_file=None, write_state=False)
        self.assertEqual(len(status.properties), 1)
        prop = status.properties[0]
        self.assertEqual(prop.property_uid, "p1")
        self.assertEqual(prop.listing_count, 2)
        self.assertEqual(prop.listed_count, 1)
        self.assertEqual(prop.next_7d_available, 2)
        self.assertEqual(prop.next_7d_blocked, 1)
        self.assertEqual(prop.next_7d_avg_price, 250.0)
        self.assertEqual(prop.next_checkin["reservation_code"], "ABC123")
        self.assertEqual(prop.new_bookings, [])
        self.assertEqual(prop.new_message_alerts, [])

    def test_build_portfolio_status_since_last_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(json.dumps({"last_run_at": "2026-04-26T08:00:00Z"}))
            status = build_portfolio_status(
                FakeClient(),
                today=date(2026, 4, 26),
                days=3,
                state_file=state_path,
                write_state=False,
            )
        prop = status.properties[0]
        self.assertEqual(status.last_run_at, "2026-04-26T08:00:00Z")
        self.assertEqual(len(prop.new_bookings), 1)
        self.assertEqual(prop.new_bookings[0]["reservation_code"], "ABC123")
        self.assertEqual(len(prop.checkouts_today), 1)
        self.assertEqual(prop.checkouts_today[0]["reservation_code"], "XYZ999")
        self.assertEqual(len(prop.new_message_alerts), 1)
        self.assertEqual(prop.new_message_alerts[0].latest_message_preview, "Can I check in early?")

    def test_format_portfolio_status_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(json.dumps({"last_run_at": "2026-04-26T08:00:00Z"}))
            status = build_portfolio_status(
                FakeClient(),
                today=date(2026, 4, 26),
                days=3,
                state_file=state_path,
                write_state=False,
            )
        text = format_portfolio_status_text(status)
        self.assertIn("Since last run: 2026-04-26T08:00:00Z", text)
        self.assertIn("New bookings since last run: 1", text)
        self.assertIn("Checkouts today: 1", text)
        self.assertIn("New messages to review: 1", text)

    def test_portfolio_status_to_dict(self):
        status = build_portfolio_status(FakeClient(), today=date(2026, 4, 26), days=3, state_file=None, write_state=False)
        payload = portfolio_status_to_dict(status)
        self.assertIn("generated_at", payload)
        self.assertEqual(len(payload["properties"]), 1)
        self.assertIn("new_bookings", payload["properties"][0])


if __name__ == "__main__":
    unittest.main()
