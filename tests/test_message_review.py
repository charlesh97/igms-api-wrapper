from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path("/Users/charleslab/.hermes/profiles/atlas/scripts/igms-message-review.py")


def load_script():
    spec = importlib.util.spec_from_file_location("atlas_igms_message_review", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise ImportError("Unable to load {}".format(SCRIPT_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


message_review = load_script()


class FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 7, 31)


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 7, 31, 9, 30)
        if tz is not None:
            return value.replace(tzinfo=tz)
        return value


class FakeClient:
    def __init__(self, threads=None, error=None):
        self.threads = list(threads or [])
        self.error = error
        self.calls = []

    def get_all_threads(self, **filters):
        self.calls.append(filters)
        if self.error is not None:
            raise self.error
        return copy.deepcopy(self.threads)


def fresh_state():
    return {"last_run": None, "seen_messages": [], "reported": {}}


def thread(
    thread_id="thread-1",
    message_id="message-1",
    sender_uid="guest-1",
    host_uid="host-1",
    text="Can you help?",
    message_dttm="2026-07-31 08:00:00",
    last_message_dttm="2026-07-31 08:00:00",
    reservation="ABC123",
    platform="airbnb",
    messages=None,
):
    if messages is None:
        messages = [
            {
                "messageId": message_id,
                "senderUid": sender_uid,
                "messageText": text,
                "messageDttm": message_dttm,
            }
        ]
    return {
        "threadId": thread_id,
        "hostUid": host_uid,
        "reservationCode": reservation,
        "platformType": platform,
        "lastMessageDttm": last_message_dttm,
        "messages": messages,
    }


class MessageReviewLogicTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 31, 9, 30)

    def test_newest_first_message_controls_guest_last_detection(self):
        guest_newest = thread(
            messages=[
                {"messageId": "new", "senderUid": "guest-1", "messageText": "new guest message"},
                {"messageId": "old", "senderUid": "host-1", "messageText": "old host message"},
            ]
        )
        host_newest = thread(
            thread_id="thread-2",
            messages=[
                {"messageId": "new-2", "senderUid": "host-1", "messageText": "new host message"},
                {"messageId": "old-2", "senderUid": "guest-1", "messageText": "old guest message"},
            ],
        )

        new_messages, unresolved, _ = message_review.analyze_threads(
            [guest_newest, host_newest], fresh_state(), self.now
        )

        self.assertEqual([item["thread_id"] for item in new_messages], ["thread-1"])
        self.assertEqual(unresolved, [])

    def test_sender_is_compared_with_each_threads_own_host_uid(self):
        first = thread(thread_id="1", sender_uid="host-a", host_uid="host-a")
        second = thread(thread_id="2", sender_uid="host-a", host_uid="host-b")

        new_messages, _, state = message_review.analyze_threads(
            [first, second], fresh_state(), self.now
        )

        self.assertEqual([item["thread_id"] for item in new_messages], ["2"])
        self.assertNotIn("1", state["reported"])
        self.assertIn("2", state["reported"])

    def test_duplicate_message_is_silent_and_new_guest_message_resets_report_clock(self):
        state = fresh_state()
        first_thread = thread(message_id="m1")

        first_new, _, state = message_review.analyze_threads([first_thread], state, self.now)
        duplicate_new, duplicate_unresolved, state = message_review.analyze_threads(
            [first_thread], state, self.now + timedelta(hours=1)
        )
        updated = thread(message_id="m2", text="One more thing")
        updated_at = self.now + timedelta(hours=2)
        second_new, _, state = message_review.analyze_threads([updated], state, updated_at)

        self.assertEqual(len(first_new), 1)
        self.assertEqual(duplicate_new, [])
        self.assertEqual(duplicate_unresolved, [])
        self.assertEqual(len(second_new), 1)
        self.assertEqual(state["seen_messages"], ["m1", "m2"])
        self.assertEqual(state["reported"]["thread-1"]["last_msg_id"], "m2")
        self.assertEqual(
            state["reported"]["thread-1"]["first_reported"],
            updated_at.isoformat(timespec="minutes"),
        )

    def test_reported_thread_under_72_hours_remains_silent(self):
        state = fresh_state()
        state["reported"] = {
            "thread-1": {
                "last_msg_id": "message-1",
                "first_reported": (self.now - timedelta(hours=72)).isoformat(timespec="minutes"),
                "reservation": "ABC123",
            }
        }

        new_messages, unresolved, updated = message_review.analyze_threads(
            [thread()], state, self.now
        )

        self.assertEqual(new_messages, [])
        self.assertEqual(unresolved, [])
        self.assertEqual(
            updated["reported"]["thread-1"]["first_reported"],
            (self.now - timedelta(hours=72)).isoformat(timespec="minutes"),
        )

    def test_reported_thread_over_72_hours_escalates_and_resets_clock(self):
        original = self.now - timedelta(hours=72, minutes=1)
        state = fresh_state()
        state["reported"] = {
            "thread-1": {
                "last_msg_id": "message-1",
                "first_reported": original.isoformat(timespec="minutes"),
                "reservation": "ABC123",
            }
        }

        new_messages, unresolved, updated = message_review.analyze_threads(
            [thread()], state, self.now
        )

        self.assertEqual(new_messages, [])
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["first_reported"], original.isoformat(timespec="minutes"))
        self.assertEqual(
            updated["reported"]["thread-1"]["first_reported"],
            self.now.isoformat(timespec="minutes"),
        )

    def test_host_last_removes_reported_entry(self):
        state = fresh_state()
        state["reported"] = {
            "thread-1": {
                "last_msg_id": "old-guest",
                "first_reported": "2026-07-25T09:30",
                "reservation": "ABC123",
            }
        }

        new_messages, unresolved, updated = message_review.analyze_threads(
            [thread(message_id="host-reply", sender_uid="host-1")], state, self.now
        )

        self.assertEqual(new_messages, [])
        self.assertEqual(unresolved, [])
        self.assertNotIn("thread-1", updated["reported"])
        self.assertIn("host-reply", updated["seen_messages"])

    def test_inquiry_without_reservation_code_is_flagged(self):
        new_messages, _, _ = message_review.analyze_threads(
            [thread(reservation=None)], fresh_state(), self.now
        )

        self.assertEqual(new_messages[0]["reservation"], "(inquiry)")

    def test_empty_and_missing_messages_are_skipped(self):
        new_messages, unresolved, state = message_review.analyze_threads(
            [thread(messages=[]), {"threadId": "missing-messages"}],
            fresh_state(),
            self.now,
        )

        self.assertEqual(new_messages, [])
        self.assertEqual(unresolved, [])
        self.assertEqual(state["seen_messages"], [])

    def test_none_and_missing_optional_fields_do_not_crash(self):
        sparse = {
            "messages": [
                {
                    "messageId": None,
                    "senderUid": "unknown-guest",
                    "messageText": None,
                    "messageDttm": None,
                }
            ]
        }

        new_messages, unresolved, updated = message_review.analyze_threads(
            [sparse], fresh_state(), self.now
        )

        self.assertEqual(unresolved, [])
        self.assertEqual(
            new_messages,
            [{
                "thread_id": "None",
                "reservation": "(inquiry)",
                "platform": "?",
                "last_message_dttm": None,
                "preview": "",
            }],
        )
        self.assertEqual(updated["seen_messages"], [])

    def test_unicode_newlines_quotes_and_long_preview_are_safe(self):
        raw = 'First line\n"Quoted" 😀 ' + ("界" * 200)

        new_messages, _, _ = message_review.analyze_threads(
            [thread(text=raw)], fresh_state(), self.now
        )

        preview = new_messages[0]["preview"]
        self.assertEqual(preview, raw.replace("\n", " ")[:150])
        self.assertEqual(len(preview), 150)
        self.assertNotIn("\n", preview)
        self.assertIn("😀", preview)


class MessageReviewStateTests(unittest.TestCase):
    def test_missing_state_file_returns_fresh_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            self.assertEqual(message_review.load_state(path), fresh_state())

    def test_corrupt_state_file_returns_fresh_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "corrupt.json"
            path.write_text("{not valid json")
            self.assertEqual(message_review.load_state(path), fresh_state())

    def test_save_state_creates_missing_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "new" / "nested" / "state.json"
            state = {"last_run": "now", "seen_messages": ["m1"], "reported": {}}

            message_review.save_state(path, state)

            self.assertEqual(json.loads(path.read_text()), state)


class MessageReviewMainTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.state_path = Path(self.temp_dir.name) / "state.json"

    def run_main(self, client=None, argv=None, init_error=None):
        fake_client = client or FakeClient()
        stdout = io.StringIO()
        args = [str(SCRIPT_PATH), "--state", str(self.state_path)]
        if argv:
            args.extend(argv)
        with mock.patch.object(message_review, "IGMSClient") as client_class, \
                mock.patch.object(message_review, "date", FixedDate), \
                mock.patch.object(message_review, "datetime", FixedDateTime), \
                mock.patch.object(sys, "argv", args), \
                contextlib.redirect_stdout(stdout):
            if init_error is not None:
                client_class.from_env.side_effect = init_error
            else:
                client_class.from_env.return_value = fake_client
            exit_code = message_review.main()
        return exit_code, stdout.getvalue(), fake_client

    def test_fetch_uses_inclusive_window_via_exclusive_tomorrow_to_date(self):
        exit_code, _, client = self.run_main(FakeClient(), ["--days", "5"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            client.calls,
            [{"fromDate": "2026-07-26", "toDate": "2026-08-01"}],
        )

    def test_default_lookback_is_seven_days(self):
        _, _, client = self.run_main(FakeClient())
        self.assertEqual(client.calls[0]["fromDate"], "2026-07-24")

    def test_silent_path_prints_exact_gate_for_already_reported_guest_message(self):
        self.state_path.write_text(json.dumps({
            "last_run": "2026-07-31T09:00",
            "seen_messages": ["message-1"],
            "reported": {
                "thread-1": {
                    "last_msg_id": "message-1",
                    "first_reported": "2026-07-31T09:00",
                    "reservation": "ABC123",
                }
            },
        }))

        exit_code, output, _ = self.run_main(FakeClient([thread()]))

        self.assertEqual(exit_code, 0)
        self.assertEqual(output, '{"wakeAgent": false}\n')

    def test_wake_path_has_stable_context_shape(self):
        exit_code, output, _ = self.run_main(FakeClient([thread()]))

        payload = json.loads(output)
        self.assertEqual(exit_code, 0)
        self.assertEqual(set(payload), {"wakeAgent", "context"})
        self.assertTrue(payload["wakeAgent"])
        self.assertEqual(payload["context"]["still_unresolved"], [])
        self.assertEqual(
            payload["context"]["new_guest_messages"],
            [{
                "thread_id": "thread-1",
                "reservation": "ABC123",
                "platform": "airbnb",
                "last_message_dttm": "2026-07-31 08:00:00",
                "preview": "Can you help?",
            }],
        )

    def test_init_failure_prints_wake_error_and_returns_one(self):
        exit_code, output, client = self.run_main(init_error=RuntimeError("no credentials"))

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            json.loads(output),
            {"wakeAgent": True, "context": {"error": "iGMS init failed: no credentials"}},
        )
        self.assertEqual(client.calls, [])

    def test_fetch_failure_prints_wake_error_and_returns_one(self):
        exit_code, output, client = self.run_main(
            FakeClient(error=RuntimeError("API unavailable"))
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            json.loads(output),
            {"wakeAgent": True, "context": {"error": "fetch threads failed: API unavailable"}},
        )
        self.assertEqual(len(client.calls), 1)
        self.assertFalse(self.state_path.exists())

    def test_debug_prints_diagnostic_line_then_normal_json(self):
        exit_code, output, _ = self.run_main(FakeClient([thread()]), ["--debug"])
        lines = output.splitlines()

        self.assertEqual(exit_code, 0)
        self.assertEqual(lines[0], "[debug] 1 threads | 1 new | 0 escalated | seen=1")
        self.assertTrue(json.loads(lines[1])["wakeAgent"])


if __name__ == "__main__":
    unittest.main()
