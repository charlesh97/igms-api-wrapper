from __future__ import annotations

import unittest

from igms_wrapper.cli import build_parser


class CLITests(unittest.TestCase):
    def test_bookings_filters_argument_parses(self):
        parser = build_parser()
        args = parser.parse_args(["bookings", "--page", "2", "--filters", '{"booking_status":"accepted"}'])
        self.assertEqual(args.cmd, "bookings")
        self.assertEqual(args.page, 2)
        self.assertEqual(args.filters, '{"booking_status":"accepted"}')

    def test_calendar_arguments_parse(self):
        parser = build_parser()
        args = parser.parse_args([
            "calendar", "--property-uid", "abc",
            "--from-date", "2026-01-01", "--to-date", "2026-01-07",
        ])
        self.assertEqual(args.property_uid, "abc")
        self.assertEqual(args.from_date, "2026-01-01")
        self.assertEqual(args.to_date, "2026-01-07")

    def test_status_arguments_parse(self):
        parser = build_parser()
        args = parser.parse_args(["status", "--days", "14", "--json"])
        self.assertEqual(args.cmd, "status")
        self.assertEqual(args.days, 14)
        self.assertTrue(args.as_json)


if __name__ == "__main__":
    unittest.main()
