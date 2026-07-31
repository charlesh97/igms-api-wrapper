"""Stateful iGMS message review — versioned logic for the daily cron.

Detects NEW guest messages (need reply) and UNRESOLVED threads (guest wrote
last and hasn't been replied to). Prints a wakeAgent gate for the Hermes cron:

  - Nothing new/unresolved  -> {"wakeAgent": false}  (0 LLM tokens, silent)
  - Action needed           -> {"wakeAgent": true, "context": {...}} (agent reviews)

State file tracks seen message IDs so a thread is only reported once per new
guest message, with an escalation re-report for threads stuck >=72h.

The deployed cron script (~/.hermes/profiles/atlas/scripts/igms-message-review.py)
is a thin wrapper that imports main() from here, so logic stays versioned in
the repo and is fully testable without a live API.
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from .client import IGMSClient

STATE_PATH = Path(
    "~/.hermes/profiles/atlas/state/igms_message_review.json"
).expanduser()
ESCALATION_HOURS = 72


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _parse_iso_naive(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO timestamp; returns a NAIVE local datetime.

    Handles both '%Y-%m-%d %H:%M:%S' (iGMS) and ISO-8601 (state file) formats,
    including timezone-bearing values from legacy state (converted to local
    naive so age comparisons against `now` never raise).
    """
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        parsed = parse_dt(text)
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _normalize_seen(value: object) -> list:
    """Coerce seen_messages to a list of str (mixed str/int IDs sort safely)."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _normalize_reported(value: object) -> dict:
    """Coerce reported to {key: {last_msg_id: str, first_reported: str, reservation}}.

    Drops scalar/non-dict legacy entries (they cannot be compared safely) and
    drops bare threadId keys (pre-platform-namespace schema) so they get
    re-reported once rather than silently suppressing an alert.
    """
    if not isinstance(value, dict):
        return {}
    normalized = {}
    for key, entry in value.items():
        if not isinstance(entry, dict):
            continue
        if ":" not in str(key):
            # Legacy bare-threadId key from before platform namespacing — drop;
            # the thread will be re-reported (fail-open, never silently missed).
            continue
        last_msg_id = entry.get("last_msg_id")
        if last_msg_id is None:
            continue
        normalized[str(key)] = {
            "last_msg_id": str(last_msg_id),
            "first_reported": str(entry.get("first_reported") or ""),
            "reservation": str(entry.get("reservation") or ""),
        }
    return normalized


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"last_run": None, "seen_messages": [], "reported": {}}
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {"last_run": None, "seen_messages": [], "reported": {}}
    if not isinstance(data, dict):
        return {"last_run": None, "seen_messages": [], "reported": {}}
    return {
        "last_run": data.get("last_run"),
        "seen_messages": _normalize_seen(data.get("seen_messages")),
        "reported": _normalize_reported(data.get("reported")),
    }


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n")


def _msg_key(thread_id: str, newest: dict) -> str:
    """Stable dedup key for a message.

    Real messageId when present; otherwise a fallback fingerprint so two
    successive ID-less guest messages are NOT silently collapsed into one
    (the old 'None' == 'None' bug).
    """
    msg_id = newest.get("messageId")
    if msg_id is not None:
        return str(msg_id)
    fingerprint = "{}|{}|{}".format(
        thread_id,
        newest.get("messageDttm") or "",
        (newest.get("messageText") or "")[:80],
    )
    return "anon:{}".format(abs(hash(fingerprint)))


def analyze_threads(
    threads: list,
    state: dict,
    now: datetime,
) -> tuple:
    """Classify threads against review state. Pure logic, no I/O or network.

    Returns (new_needing_reply, still_unresolved, anomalies, updated_state).

    - Threads whose newest message is from the guest and was never reported are
      added to new_needing_reply and marked reported (clock starts at now).
    - A NEW guest message in an already-reported thread is reported again and
      the escalation clock resets.
    - An already-reported thread still guest-last after ESCALATION_HOURS lands
      in still_unresolved and the clock resets (>= boundary: a daily cron run
      exactly 72h after first report must escalate, not wait another day).
    - Host-last threads are resolved: their reported entry is cleared.
    - Report state is namespaced by platform:threadId so cross-platform ID
      collisions cannot overwrite/clear each other's clocks.
    - Threads with a lastMessageDttm but an empty/missing messages array cannot
      be classified — they surface as ANOMALIES so main() wakes with
      diagnostic context instead of treating the fetch as clean.
    """
    seen = set(_normalize_seen(state.get("seen_messages", [])))
    reported = _normalize_reported(state.get("reported", {}))

    new_needing_reply = []
    still_unresolved = []
    anomalies = []

    for t in threads:
        msgs = t.get("messages") or []
        thread_id = str(t.get("threadId"))
        code = t.get("reservationCode") or "(inquiry)"
        platform = t.get("platformType", "?")
        report_key = "{}:{}".format(platform, thread_id)

        if not msgs:
            # Cannot classify. If iGMS claims activity on this thread, that is
            # a partial-response/schema problem — fail OPEN (wake with context).
            if t.get("lastMessageDttm"):
                anomalies.append({
                    "thread_id": thread_id,
                    "reservation": code,
                    "platform": platform,
                    "last_message_dttm": t.get("lastMessageDttm"),
                    "reason": "thread has activity but no messages array",
                })
            continue

        newest = msgs[0]
        msg_key = _msg_key(thread_id, newest)
        host_uid = t.get("hostUid")
        sender = newest.get("senderUid", "")
        is_from_host = sender == host_uid
        preview = (newest.get("messageText") or "").replace("\n", " ")[:150]

        # Track all seen message keys (real IDs and anon fingerprints)
        seen.add(msg_key)

        if is_from_host:
            # Host wrote last — thread resolved (or auto-message). Clear report state.
            reported.pop(report_key, None)
            continue

        # Guest wrote last — needs reply
        thread_info = {
            "thread_id": thread_id,
            "reservation": code,
            "platform": platform,
            "last_message_dttm": newest.get("messageDttm") or t.get("lastMessageDttm"),
            "preview": preview,
        }

        prev = reported.get(report_key)
        if prev is None or msg_key != prev.get("last_msg_id"):
            # New guest message not yet reported
            new_needing_reply.append(thread_info)
            reported[report_key] = {
                "last_msg_id": msg_key,
                "first_reported": now.isoformat(timespec="minutes"),
                "reservation": code,
            }
        else:
            # Already reported — escalate only if still unresolved after threshold
            first = _parse_iso_naive(prev.get("first_reported"))
            age_hours = (now - first).total_seconds() / 3600 if first else 0.0
            if age_hours >= ESCALATION_HOURS:
                still_unresolved.append({**thread_info, "first_reported": prev.get("first_reported")})
                reported[report_key]["first_reported"] = now.isoformat(timespec="minutes")  # reset escalation clock

    state["seen_messages"] = sorted(seen)
    state["reported"] = reported
    return new_needing_reply, still_unresolved, anomalies, state


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily iGMS message review")
    parser.add_argument("--days", type=int, default=7, help="Look-back window (default 7; must exceed ESCALATION_HOURS/24 so unresolved threads stay visible)")
    parser.add_argument("--state", default=str(STATE_PATH), help="State file path")
    parser.add_argument("--debug", action="store_true", help="Print full thread data for debugging")
    args = parser.parse_args()

    try:
        client = IGMSClient.from_env()
    except Exception as e:
        print(json.dumps({"wakeAgent": True, "context": {"error": "iGMS init failed: {}".format(e)}}))
        return 1

    today = date.today()
    state = load_state(Path(args.state))
    now = datetime.now()

    try:
        threads = client.get_all_threads(
            fromDate=(today - timedelta(days=args.days)).isoformat(),
            # NOTE: iGMS toDate is EXCLUSIVE of that day — must pass tomorrow
            # so today's messages are included (verified 2026-07-31).
            toDate=(today + timedelta(days=1)).isoformat(),
        )
    except Exception as e:
        # Serialize with json.dumps so quotes/newlines in the error cannot
        # produce an unparseable gate (fail-open must stay parseable).
        print(json.dumps({"wakeAgent": True, "context": {"error": "fetch threads failed: {}".format(e)}}))
        return 1

    new_needing_reply, still_unresolved, anomalies, state = analyze_threads(threads, state, now)

    # Persist state
    state["last_run"] = now.isoformat(timespec="minutes")
    save_state(Path(args.state), state)

    if args.debug:
        print("[debug] {} threads | {} new | {} escalated | {} anomalies | seen={}".format(
            len(threads), len(new_needing_reply), len(still_unresolved),
            len(anomalies), len(state["seen_messages"]),
        ))

    if not new_needing_reply and not still_unresolved and not anomalies:
        # SILENT — nothing to report
        print('{"wakeAgent": false}')
        return 0

    context = {
        "new_guest_messages": new_needing_reply,
        "still_unresolved": still_unresolved,
        "anomalies": anomalies,
    }
    print(json.dumps({"wakeAgent": True, "context": context}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
