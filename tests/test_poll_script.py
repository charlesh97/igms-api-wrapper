from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import unittest
from datetime import date
from unittest import mock

from igms_wrapper.poll_messages import main as poll_main


class FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 7, 31)


class FakeClient:
    def __init__(self, threads=None):
        self.threads = list(threads or [])
        self.calls = []

    def get_all_threads(self, **filters):
        self.calls.append(filters)
        return copy.deepcopy(self.threads)


def thread(
    *,
    reservation="ABC123",
    host_uid="host-1",
    messages=None,
    thread_id="thread-1",
):
    if messages is None:
        messages = [{
            "messageId": "message-1",
            "senderUid": "guest-1",
            "messageText": "Can I check in early?",
            "messageDttm": "2026-07-31 08:00:00",
        }]
    return {
        "threadId": thread_id,
        "hostUid": host_uid,
        "reservationCode": reservation,
        "platformType": "airbnb",
        "lastMessageDttm": "2026-07-31 08:00:00",
        "messages": messages,
    }


class PollScriptTests(unittest.TestCase):
    def run_main(self, threads=None, argv=None):
        client = FakeClient(threads)
        stdout = io.StringIO()
        args = ["poll_igms_messages.py"] + list(argv or [])
        with mock.patch.object(poll_main.__module__ and sys.modules["igms_wrapper.poll_messages"], "IGMSClient") as client_class, \
                mock.patch.object(sys.modules["igms_wrapper.poll_messages"], "date", FixedDate), \
                mock.patch.object(sys, "argv", args), \
                contextlib.redirect_stdout(stdout):
            client_class.from_env.return_value = client
            exit_code = poll_main()
        return exit_code, stdout.getvalue(), client

    def test_guest_last_uses_messages_zero_not_last_item(self):
        messages = [
            {"senderUid": "guest-1", "messageText": "new guest"},
            {"senderUid": "host-1", "messageText": "old host"},
        ]

        exit_code, output, _ = self.run_main([thread(messages=messages)], ["--json"])

        payload = json.loads(output)
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(payload["needs_reply"]), 1)
        self.assertEqual(payload["needs_reply"][0]["preview"], "new guest")

    def test_host_last_is_not_flagged_even_when_older_message_is_guest(self):
        messages = [
            {"senderUid": "host-1", "messageText": "new host"},
            {"senderUid": "guest-1", "messageText": "old guest"},
        ]

        _, output, _ = self.run_main([thread(messages=messages)], ["--json"])

        payload = json.loads(output)
        self.assertEqual(payload["threads"][0]["last_sender"], "HOST")
        self.assertEqual(payload["needs_reply"], [])

    def test_days_cutoff_and_exclusive_to_date_are_passed_exactly(self):
        exit_code, _, client = self.run_main([], ["--days", "10"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            client.calls,
            [{"fromDate": "2026-07-21", "toDate": "2026-08-01"}],
        )

    def test_json_output_is_valid_and_contains_both_collections(self):
        _, output, _ = self.run_main([thread()], ["--json"])

        payload = json.loads(output)

        self.assertEqual(set(payload), {"threads", "needs_reply"})
        self.assertEqual(len(payload["threads"]), 1)

    def test_empty_result_prints_sane_empty_table_message(self):
        exit_code, output, _ = self.run_main([], ["--days", "4"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(output, "No iGMS message activity in the last 4 day(s).\n")

    def test_inquiry_without_reservation_code_renders(self):
        _, output, _ = self.run_main([thread(reservation=None)])

        self.assertIn("(inquiry)", output)
        self.assertIn("GUEST", output)
        self.assertIn("1 thread(s) where the GUEST wrote last", output)


if __name__ == "__main__":
    unittest.main()
