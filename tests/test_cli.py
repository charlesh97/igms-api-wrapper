from __future__ import annotations

import contextlib
import io
import unittest

from igms_wrapper.cli import build_parser, main


class CLITests(unittest.TestCase):
    def test_uid_inventory_command_parses(self):
        parser = build_parser()
        args = parser.parse_args(["uid-inventory"])
        self.assertEqual(args.cmd, "uid-inventory")

    def test_listings_all_and_filters_parse(self):
        parser = build_parser()
        args = parser.parse_args([
            "listings", "--all", "--filters", '{"platform_type":"airbnb"}',
        ])
        self.assertTrue(args.all_pages)
        self.assertEqual(args.filters, '{"platform_type":"airbnb"}')

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

    def test_main_returns_2_for_invalid_json_filters(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = main(["bookings", "--filters", "{not-json}"])
        self.assertEqual(exit_code, 2)
        self.assertIn("Invalid JSON", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
