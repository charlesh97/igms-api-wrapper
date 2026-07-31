from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

from igms_wrapper.message_review import (
    ESCALATION_HOURS,
    analyze_threads,
    load_state,
    save_state,
)


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

    def analyze(self, threads, state=None, now=None):
        return analyze_threads(threads, state or fresh_state(), now or self.now)

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

        new_messages, unresolved, anomalies, _ = self.analyze([guest_newest, host_newest])

        self.assertEqual([item["thread_id"] for item in new_messages], ["thread-1"])
        self.assertEqual(unresolved, [])
        self.assertEqual(anomalies, [])

    def test_sender_is_compared_with_each_threads_own_host_uid(self):
        first = thread(thread_id="1", sender_uid="host-a", host_uid="host-a")
        second = thread(thread_id="2", sender_uid="host-a", host_uid="host-b")

        new_messages, _, _, state = self.analyze([first, second])

        self.assertEqual([item["thread_id"] for item in new_messages], ["2"])
        self.assertNotIn("airbnb:1", state["reported"])
        self.assertIn("airbnb:2", state["reported"])

    def test_report_state_is_namespaced_by_platform(self):
        """Same threadId on two platforms must not collide/overwrite."""
        airbnb = thread(thread_id="7", platform="airbnb", message_id="m-airbnb")
        vrbo = thread(thread_id="7", platform="vrbo", message_id="m-vrbo")

        new_messages, _, _, state = self.analyze([airbnb, vrbo])

        self.assertEqual(len(new_messages), 2)
        self.assertIn("airbnb:7", state["reported"])
        self.assertIn("vrbo:7", state["reported"])
        self.assertEqual(state["reported"]["airbnb:7"]["last_msg_id"], "m-airbnb")
        self.assertEqual(state["reported"]["vrbo:7"]["last_msg_id"], "m-vrbo")

    def test_duplicate_message_is_silent_and_new_guest_message_resets_report_clock(self):
        state = fresh_state()
        first_thread = thread(message_id="m1")

        first_new, _, _, state = self.analyze([first_thread], state)
        duplicate_new, duplicate_unresolved, _, state = self.analyze(
            [first_thread], state, self.now + timedelta(hours=1)
        )
        updated = thread(message_id="m2", text="One more thing")
        updated_at = self.now + timedelta(hours=2)
        second_new, _, _, state = self.analyze([updated], state, updated_at)

        self.assertEqual(len(first_new), 1)
        self.assertEqual(duplicate_new, [])
        self.assertEqual(duplicate_unresolved, [])
        self.assertEqual(len(second_new), 1)
        self.assertEqual(state["seen_messages"], ["m1", "m2"])
        self.assertEqual(state["reported"]["airbnb:thread-1"]["last_msg_id"], "m2")
        self.assertEqual(
            state["reported"]["airbnb:thread-1"]["first_reported"],
            updated_at.isoformat(timespec="minutes"),
        )

    def test_two_idless_messages_in_same_thread_both_wake(self):
        """Regression: successive guest messages with messageId=None must BOTH
        be reported — the old 'None' == 'None' dedup silently dropped the second."""
        state = fresh_state()
        first = thread(message_id=None, text="First question", message_dttm="2026-07-31 08:00:00")

        first_new, _, _, state = self.analyze([first], state)
        second = thread(message_id=None, text="Second question", message_dttm="2026-07-31 08:30:00")
        second_new, _, _, state = self.analyze([second], state, self.now + timedelta(hours=1))

        self.assertEqual(len(first_new), 1)
        self.assertEqual(len(second_new), 1)
        self.assertNotEqual(
            state["reported"]["airbnb:thread-1"]["last_msg_id"],
            "None",
        )

    def test_reported_thread_under_72_hours_remains_silent(self):
        state = fresh_state()
        state["reported"] = {
            "airbnb:thread-1": {
                "last_msg_id": "message-1",
                "first_reported": (self.now - timedelta(hours=71, minutes=59)).isoformat(timespec="minutes"),
                "reservation": "ABC123",
            }
        }

        new_messages, unresolved, _, updated = self.analyze([thread()], state)

        self.assertEqual(new_messages, [])
        self.assertEqual(unresolved, [])
        self.assertEqual(
            updated["reported"]["airbnb:thread-1"]["first_reported"],
            (self.now - timedelta(hours=71, minutes=59)).isoformat(timespec="minutes"),
        )

    def test_reported_thread_at_exactly_72_hours_escalates(self):
        """Boundary: >= 72h must escalate — a daily cron aligned exactly at 72h
        must not postpone escalation another day (strict > would do that)."""
        original = self.now - timedelta(hours=72)
        state = fresh_state()
        state["reported"] = {
            "airbnb:thread-1": {
                "last_msg_id": "message-1",
                "first_reported": original.isoformat(timespec="minutes"),
                "reservation": "ABC123",
            }
        }

        new_messages, unresolved, _, updated = self.analyze([thread()], state)

        self.assertEqual(new_messages, [])
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["first_reported"], original.isoformat(timespec="minutes"))
        self.assertEqual(
            updated["reported"]["airbnb:thread-1"]["first_reported"],
            self.now.isoformat(timespec="minutes"),
        )

    def test_reported_thread_over_72_hours_escalates_and_resets_clock(self):
        original = self.now - timedelta(hours=72, minutes=1)
        state = fresh_state()
        state["reported"] = {
            "airbnb:thread-1": {
                "last_msg_id": "message-1",
                "first_reported": original.isoformat(timespec="minutes"),
                "reservation": "ABC123",
            }
        }

        new_messages, unresolved, _, updated = self.analyze([thread()], state)

        self.assertEqual(new_messages, [])
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["first_reported"], original.isoformat(timespec="minutes"))
        self.assertEqual(
            updated["reported"]["airbnb:thread-1"]["first_reported"],
            self.now.isoformat(timespec="minutes"),
        )

    def test_legacy_timezone_aware_first_reported_escalates(self):
        """Regression: tz-aware legacy timestamps used to crash naive-vs-aware
        comparison; they must be normalized and still escalate."""
        state = fresh_state()
        state["reported"] = {
            "airbnb:thread-1": {
                "last_msg_id": "message-1",
                "first_reported": "2026-07-28T09:30:00+00:00",
                "reservation": "ABC123",
            }
        }

        new_messages, unresolved, _, _ = self.analyze([thread()], state)

        self.assertEqual(new_messages, [])
        self.assertEqual(len(unresolved), 1)

    def test_host_last_removes_reported_entry(self):
        state = fresh_state()
        state["reported"] = {
            "airbnb:thread-1": {
                "last_msg_id": "old-guest",
                "first_reported": "2026-07-25T09:30",
                "reservation": "ABC123",
            }
        }

        new_messages, unresolved, _, updated = self.analyze(
            [thread(message_id="host-reply", sender_uid="host-1")], state
        )

        self.assertEqual(new_messages, [])
        self.assertEqual(unresolved, [])
        self.assertNotIn("airbnb:thread-1", updated["reported"])
        self.assertIn("host-reply", updated["seen_messages"])

    def test_inquiry_without_reservation_code_is_flagged(self):
        new_messages, _, _, _ = self.analyze([thread(reservation=None)])

        self.assertEqual(new_messages[0]["reservation"], "(inquiry)")

    def test_empty_and_missing_messages_are_skipped(self):
        # No lastMessageDttm => no claimed activity => benign skip
        new_messages, unresolved, anomalies, state = self.analyze(
            [
                {"threadId": "empty-no-activity", "messages": []},
                {"threadId": "missing-messages"},
            ],
        )

        self.assertEqual(new_messages, [])
        self.assertEqual(unresolved, [])
        self.assertEqual(anomalies, [])
        self.assertEqual(state["seen_messages"], [])

    def test_thread_with_activity_but_no_messages_is_anomaly(self):
        """Fail open: iGMS claims activity (lastMessageDttm) but returned no
        messages array — must surface as an anomaly, not silent skip."""
        partial = {
            "threadId": "thread-x",
            "reservationCode": "CODE1",
            "platformType": "airbnb",
            "lastMessageDttm": "2026-07-31 08:00:00",
            "messages": [],
        }

        new_messages, unresolved, anomalies, _ = self.analyze([partial])

        self.assertEqual(new_messages, [])
        self.assertEqual(unresolved, [])
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["thread_id"], "thread-x")
        self.assertEqual(anomalies[0]["reason"], "thread has activity but no messages array")

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

        new_messages, unresolved, _, updated = self.analyze([sparse])

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
        # Anon fingerprint is recorded, NOT "None" (the old silent-miss bug)
        self.assertEqual(len(updated["seen_messages"]), 1)
        self.assertTrue(updated["seen_messages"][0].startswith("anon:"))

    def test_unicode_newlines_quotes_and_long_preview_are_safe(self):
        raw = 'First line\n"Quoted" 😀 ' + ("界" * 200)

        new_messages, _, _, _ = self.analyze([thread(text=raw)])

        preview = new_messages[0]["preview"]
        self.assertEqual(preview, raw.replace("\n", " ")[:150])
        self.assertEqual(len(preview), 150)
        self.assertNotIn("\n", preview)
        self.assertIn("😀", preview)


class MessageReviewStateTests(unittest.TestCase):
    def test_missing_state_file_returns_fresh_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            self.assertEqual(load_state(path), fresh_state())

    def test_corrupt_state_file_returns_fresh_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "corrupt.json"
            path.write_text("{not valid json")
            self.assertEqual(load_state(path), fresh_state())

    def test_save_state_creates_missing_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "new" / "nested" / "state.json"
            state = {"last_run": "now", "seen_messages": ["m1"], "reported": {}}

            save_state(path, state)

            self.assertEqual(json.loads(path.read_text()), state)

    def test_load_state_normalizes_seen_messages_to_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(json.dumps({
                "last_run": "2026-07-31T09:00",
                "seen_messages": [123, "456", None],
                "reported": {},
            }))

            state = load_state(path)

            self.assertEqual(state["seen_messages"], ["123", "456"])

    def test_load_state_drops_scalar_and_legacy_bare_key_reported_entries(self):
        """Valid-but-legacy schema must not crash analysis; bare threadId keys
        (pre-platform-namespace) are dropped so the thread re-reports (fail open)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(json.dumps({
                "last_run": "2026-07-31T09:00",
                "seen_messages": [],
                "reported": {
                    "bare-thread-1": {"last_msg_id": "m1", "first_reported": "x", "reservation": "A"},
                    "airbnb:thread-2": {"last_msg_id": 42, "first_reported": "2026-07-30T09:00", "reservation": "B"},
                    "scalar-entry": "not-a-dict",
                },
            }))

            state = load_state(path)

            self.assertNotIn("bare-thread-1", state["reported"])
            self.assertNotIn("scalar-entry", state["reported"])
            self.assertEqual(state["reported"]["airbnb:thread-2"]["last_msg_id"], "42")

    def test_load_state_handles_null_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(json.dumps({"seen_messages": None, "reported": None}))

            state = load_state(path)

            self.assertEqual(state["seen_messages"], [])
            self.assertEqual(state["reported"], {})

    def test_load_state_accepts_non_dict_json_gracefully(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(json.dumps([1, 2, 3]))

            self.assertEqual(load_state(path), fresh_state())


class MessageReviewMainTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.state_path = Path(self.temp_dir.name) / "state.json"

    def run_main(self, client=None, argv=None, init_error=None):
        import igms_wrapper.message_review as message_review
        fake_client = client or FakeClient()
        stdout = io.StringIO()
        args = ["igms-message-review.py", "--state", str(self.state_path)]
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
                "airbnb:thread-1": {
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
        self.assertEqual(payload["context"]["anomalies"], [])
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

    def test_anomaly_wakes_agent(self):
        partial = {
            "threadId": "thread-x",
            "reservationCode": "CODE1",
            "platformType": "airbnb",
            "lastMessageDttm": "2026-07-31 08:00:00",
            "messages": [],
        }

        exit_code, output, _ = self.run_main(FakeClient([partial]))

        payload = json.loads(output)
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["wakeAgent"])
        self.assertEqual(len(payload["context"]["anomalies"]), 1)
        self.assertEqual(payload["context"]["new_guest_messages"], [])
        self.assertEqual(payload["context"]["still_unresolved"], [])

    def test_init_failure_prints_wake_error_and_returns_one(self):
        exit_code, output, client = self.run_main(init_error=RuntimeError("no credentials"))

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            json.loads(output),
            {"wakeAgent": True, "context": {"error": "iGMS init failed: no credentials"}},
        )
        self.assertEqual(client.calls, [])

    def test_init_failure_with_json_special_chars_stays_parseable(self):
        """Errors containing quotes/newlines must not corrupt the JSON gate."""
        exit_code, output, _ = self.run_main(init_error=RuntimeError('bad "quote" \n newline'))

        self.assertEqual(exit_code, 1)
        payload = json.loads(output)  # must not raise
        self.assertTrue(payload["wakeAgent"])
        self.assertIn("bad", payload["context"]["error"])

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
        self.assertEqual(lines[0], "[debug] 1 threads | 1 new | 0 escalated | 0 anomalies | seen=1")
        self.assertTrue(json.loads(lines[1])["wakeAgent"])


if __name__ == "__main__":
    unittest.main()
