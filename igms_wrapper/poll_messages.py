"""Poll iGMS message threads for Atlas STR properties — versioned logic.

Flags threads where the GUEST wrote last (needs reply) and prints a summary.
The deployed skill script (poll_igms_messages.py) is a thin wrapper that
imports main() from here so logic stays versioned and testable.

Usage:
    python3 -m igms_wrapper.poll_messages [--days N] [--json]
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from typing import Optional

from .client import IGMSClient


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def collect_threads(client, days: int) -> list:
    """Fetch threads since the look-back window (toDate=tomorrow for inclusivity)."""
    today = date.today()
    cutoff = today - timedelta(days=days)
    threads = client.get_all_threads(
        fromDate=cutoff.isoformat(),
        # NOTE: iGMS toDate is EXCLUSIVE of that day — pass tomorrow so
        # today's messages are included (verified 2026-07-31).
        toDate=(today + timedelta(days=1)).isoformat(),
    )
    # Sort by most recent activity
    threads.sort(key=lambda t: t.get("lastMessageDttm") or t.get("updateDttm") or "", reverse=True)
    return threads


def build_rows(threads: list) -> tuple:
    """Convert threads to display rows; returns (rows, needs_reply)."""
    rows = []
    needs_reply = []
    for t in threads:
        msgs = t.get("messages") or []
        newest = msgs[0] if msgs else {}
        host_uid = t.get("hostUid")
        sender = newest.get("senderUid", "")
        is_host = sender == host_uid
        last_dt = t.get("lastMessageDttm") or t.get("updateDttm") or "N/A"
        code = t.get("reservationCode") or "(inquiry)"
        text = (newest.get("messageText") or "").replace("\n", " ")[:100]

        row = {
            "last": last_dt,
            "reservation": code,
            "platform": t.get("platformType", "?"),
            "last_sender": "HOST" if is_host else "GUEST",
            "preview": text,
        }
        rows.append(row)
        if not is_host and msgs:
            needs_reply.append(row)
    return rows, needs_reply


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll iGMS message threads")
    parser.add_argument("--days", type=int, default=3, help="How far back to look (default 3)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of table")
    args = parser.parse_args()

    try:
        client = IGMSClient.from_env()
    except Exception as e:
        print(f"ERROR: Failed to init iGMS client: {e}", file=sys.stderr)
        return 1

    try:
        threads = collect_threads(client, args.days)
    except Exception as e:
        print(f"ERROR: Failed to fetch threads: {e}", file=sys.stderr)
        return 1

    rows, needs_reply = build_rows(threads)

    if args.json:
        print(json.dumps({"threads": rows, "needs_reply": needs_reply}, indent=2))
        return 0

    if not rows:
        print(f"No iGMS message activity in the last {args.days} day(s).")
        return 0

    print(f"iGMS threads with activity in last {args.days} day(s): {len(rows)}")
    print(f"{'LAST ACTIVITY':<20} {'RESERVATION':<16} {'PLATFORM':<10} {'SENDER':<6} MESSAGE")
    print("-" * 110)
    for r in rows:
        flag = "⚠️ " if r in needs_reply else "   "
        print(f"{flag}{r['last']:<18} {r['reservation']:<16} {r['platform']:<10} {r['last_sender']:<6} {r['preview']}")

    if needs_reply:
        print()
        print(f"⚠️  {len(needs_reply)} thread(s) where the GUEST wrote last (may need a reply):")
        for r in needs_reply:
            print(f"  - {r['reservation']} ({r['last']}) — {r['preview']}")
    else:
        print()
        print("No guest-last threads — nothing waiting on a reply.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
