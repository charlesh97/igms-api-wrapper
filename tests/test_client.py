from __future__ import annotations

import unittest

from igms_wrapper.client import IGMSClient, IGMSConfig, _has_next_page, normalize_human_name


class FakeResponse:
    def __init__(self, payload, url="https://www.igms.com/api/test", status_code=200):
        self._payload = payload
        self.url = url
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, params=None, json=None, timeout=None):
        self.calls.append({"method": method, "url": url, "params": params, "json": json, "timeout": timeout})
        return self.responses.pop(0)


class ClientTests(unittest.TestCase):
    def test_request_appends_access_token_query_param(self):
        session = FakeSession([FakeResponse({"ok": True})])
        client = IGMSClient(config=IGMSConfig(access_token="token-123"), session=session)

        response = client.request("/api/v1/listings", params={"page": 1})

        self.assertEqual(response.payload, {"ok": True})
        self.assertEqual(session.calls[0]["params"]["access_token"], "token-123")
        self.assertEqual(session.calls[0]["params"]["page"], 1)

    def test_iter_paginated_follows_has_next_page(self):
        session = FakeSession([
            FakeResponse({"data": [{"id": 1}], "meta": {"has_next_page": True}}),
            FakeResponse({"data": [{"id": 2}], "meta": {"has_next_page": False}}),
        ])
        client = IGMSClient(config=IGMSConfig(access_token="token-123"), session=session)

        items = list(client.iter_paginated(client.get_listings))

        self.assertEqual(items, [{"id": 1}, {"id": 2}])
        self.assertEqual(session.calls[0]["params"]["page"], 1)
        self.assertEqual(session.calls[1]["params"]["page"], 2)

    def test_has_next_page_treats_falsey_strings_and_zero_as_false(self):
        self.assertFalse(_has_next_page({"meta": {"has_next_page": "false"}}, 1, 1))
        self.assertFalse(_has_next_page({"meta": {"hasNextPage": "0"}}, 1, 1))
        self.assertFalse(_has_next_page({"meta": {"next_page": 0}}, 1, 1))

    def test_find_helpers_use_normalized_name_matching(self):
        client = IGMSClient(config=IGMSConfig(access_token="token-123"), session=FakeSession([]))
        properties = [
            {"property_uid": "p1", "name": "Cozy Modern Single Family 5 Bedroom Home"},
            {"property_uid": "p2", "name": "Frosty Pines Cabin: 2br Retreat"},
        ]
        listings = [
            {"listing_uid": "l1", "listing_name": "Cozy Modern Single Family | 5BD 2BA | Close to DC"},
            {"listing_uid": "l2", "listing_name": "Frosty Pines Cabin Cozy 2 Bedroom Family Retreat"},
        ]

        property_match = client.find_property_by_name("frosty pines cabin 2br retreat", properties=properties)
        listing_match = client.find_listing_by_name("close to dc", listings=listings)

        self.assertEqual(property_match["property_uid"], "p2")
        self.assertEqual(listing_match["listing_uid"], "l1")

    def test_find_helpers_respect_explicit_empty_collections(self):
        client = IGMSClient(config=IGMSConfig(access_token="token-123"), session=FakeSession([]))

        self.assertIsNone(client.find_property_by_name("missing", properties=[]))
        self.assertIsNone(client.find_listing_by_name("missing", listings=[]))

    def test_normalize_human_name_collapses_punctuation(self):
        self.assertEqual(normalize_human_name("Frosty Pines Cabin: 2br Retreat"), "frosty pines cabin 2br retreat")

    def test_message_booking_guest_posts_json_body_with_thread_id(self):
        session = FakeSession([FakeResponse({"message_uid": "msg-1"})])
        client = IGMSClient(config=IGMSConfig(access_token="token-123"), session=session)

        payload = client.message_booking_guest("Hi there!", thread_id="thread-9")

        self.assertEqual(payload, {"message_uid": "msg-1"})
        call = session.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["url"], "https://www.igms.com/api/v1/message-booking-guest")
        self.assertEqual(call["params"]["access_token"], "token-123")
        self.assertEqual(call["json"], {"message": "Hi there!", "thread_id": "thread-9"})

    def test_message_booking_guest_with_booking_uid_and_channel(self):
        session = FakeSession([FakeResponse({"ok": True})])
        client = IGMSClient(config=IGMSConfig(access_token="token-123"), session=session)

        client.message_booking_guest("Hello", booking_uid="bk-5", channel="email")

        call = session.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["json"], {"message": "Hello", "booking_uid": "bk-5", "channel": "email"})

    def test_message_booking_guest_requires_target_and_nonempty_message(self):
        client = IGMSClient(config=IGMSConfig(access_token="token-123"), session=FakeSession([]))

        with self.assertRaises(ValueError):
            client.message_booking_guest("Hi")
        with self.assertRaises(ValueError):
            client.message_booking_guest("", thread_id="thread-9")
        with self.assertRaises(ValueError):
            client.message_booking_guest("   ", booking_uid="bk-5")

    def test_get_message_status_passes_message_uid(self):
        session = FakeSession([FakeResponse({"status": "sent"})])
        client = IGMSClient(config=IGMSConfig(access_token="token-123"), session=session)

        payload = client.get_message_status("msg-1")

        self.assertEqual(payload, {"status": "sent"})
        call = session.calls[0]
        self.assertEqual(call["method"], "GET")
        self.assertEqual(call["url"], "https://www.igms.com/api/v1/message-status")
        self.assertEqual(call["params"]["message_uid"], "msg-1")


if __name__ == "__main__":
    unittest.main()
