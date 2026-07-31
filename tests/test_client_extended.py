from __future__ import annotations

import unittest

from igms_wrapper.client import (
    IGMSAPIError,
    IGMSClient,
    IGMSConfig,
    _has_next_page,
    _records_from_payload,
)


class FakeResponse:
    def __init__(
        self,
        payload=None,
        *,
        text=None,
        json_error=None,
        http_error=None,
        status_code=200,
        url="https://www.igms.com/api/test",
    ):
        self._payload = payload
        self.text = str(payload) if text is None else text
        self._json_error = json_error
        self._http_error = http_error
        self.status_code = status_code
        self.url = url

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload

    def raise_for_status(self):
        if self._http_error is not None:
            raise self._http_error


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, params=None, json=None, timeout=None):
        self.calls.append({
            "method": method,
            "url": url,
            "params": params,
            "json": json,
            "timeout": timeout,
        })
        return self.responses.pop(0)


def make_client(responses=None):
    session = FakeSession(responses or [])
    client = IGMSClient(config=IGMSConfig(access_token="token-123"), session=session)
    return client, session


class RequestExtendedTests(unittest.TestCase):
    def test_request_passes_token_json_body_post_method_and_timeout(self):
        client, session = make_client([FakeResponse({"ok": True})])

        response = client.request(
            "/api/v1/example",
            params={"page": 2},
            method="post",
            json_body={"answer": 42},
        )

        self.assertEqual(response.payload, {"ok": True})
        self.assertEqual(session.calls, [{
            "method": "POST",
            "url": "https://www.igms.com/api/v1/example",
            "params": {"page": 2, "access_token": "token-123"},
            "json": {"answer": 42},
            "timeout": 30,
        }])

    def test_non_json_response_uses_response_text(self):
        client, _ = make_client([
            FakeResponse(text="not-json", json_error=ValueError("invalid JSON"))
        ])

        response = client.request("/api/v1/example")

        self.assertEqual(response.payload, "not-json")

    def test_http_error_from_raise_for_status_propagates(self):
        expected = RuntimeError("503 Server Error")
        client, _ = make_client([FakeResponse({"error": "down"}, http_error=expected)])

        with self.assertRaises(RuntimeError) as raised:
            client.request("/api/v1/example")

        self.assertIs(raised.exception, expected)

    def test_http_200_error_body_raises_instead_of_silent_empty(self):
        # iGMS sometimes reports application errors inside an HTTP 200 payload.
        # A silent empty record list would let the message review print
        # wakeAgent=false and skip a whole day — must RAISE (fail open).
        payload = {"error": {"code": "invalid_filter", "message": "Bad filter"}}
        client, _ = make_client()

        with self.assertRaises(IGMSAPIError) as raised:
            client.collect_paginated(lambda page: payload)

        self.assertIn("Bad filter", str(raised.exception))

    def test_http_200_string_error_body_raises(self):
        payload = {"error": "unauthorized"}
        client, _ = make_client()

        with self.assertRaises(IGMSAPIError):
            client.collect_paginated(lambda page: payload)

    def test_payload_with_data_key_is_not_treated_as_error(self):
        # Some endpoints return {"error": ...} as a DATA field; only a
        # top-level error WITHOUT data is a hard failure. Include meta so
        # the paginator terminates (real iGMS responses always carry it).
        payload = {"data": [{"error": "not really", "id": 1}], "meta": {"hasNextPage": False}}
        client, _ = make_client()

        records = client.collect_paginated(lambda page: payload)

        self.assertEqual(len(records), 1)


class PayloadExtractionTests(unittest.TestCase):
    def test_extracts_list_payload_and_filters_non_dict_items(self):
        self.assertEqual(
            _records_from_payload([{"id": 1}, None, "bad", {"id": 2}]),
            [{"id": 1}, {"id": 2}],
        )

    def test_extracts_each_known_record_key(self):
        for key in ("data", "results", "items", "records"):
            with self.subTest(key=key):
                self.assertEqual(
                    _records_from_payload({key: [{"id": 1}, 7, {"id": 2}]}),
                    [{"id": 1}, {"id": 2}],
                )

    def test_extracts_single_unknown_list_value(self):
        self.assertEqual(
            _records_from_payload({"custom": [{"id": 1}, "bad"], "meta": {}}),
            [{"id": 1}],
        )

    def test_dict_without_exactly_one_list_has_no_records(self):
        cases = [
            {"ok": True},
            {"first": [{"id": 1}], "second": [{"id": 2}]},
            "not-a-dict",
            None,
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                self.assertEqual(_records_from_payload(payload), [])


class PaginationExtendedTests(unittest.TestCase):
    def test_has_next_page_coerces_boolean_integer_and_string_flags(self):
        cases = [
            ({"meta": {"has_next_page": True}}, True),
            ({"meta": {"has_next_page": False}}, False),
            ({"meta": {"hasNextPage": 1}}, True),
            ({"meta": {"hasNextPage": 0}}, False),
            ({"meta": {"has_next_page": "YES"}}, True),
            ({"meta": {"has_next_page": " false "}}, False),
            ({"meta": {"hasNextPage": "null"}}, False),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                self.assertEqual(_has_next_page(payload, 1, 1), expected)

    def test_has_next_page_supports_next_page_key_variants(self):
        cases = [
            ({"meta": {"next_page": 2}}, True),
            ({"meta": {"next_page": 0}}, False),
            ({"meta": {"nextPage": "3"}}, True),
            ({"meta": {"nextPage": "none"}}, False),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                self.assertEqual(_has_next_page(payload, 1, 1), expected)

    def test_has_next_page_uses_meta_page_total_pages_and_record_heuristic(self):
        self.assertTrue(_has_next_page({"meta": {"page": 3}}, 2, 0))
        self.assertTrue(_has_next_page({"meta": {"total_pages": 3}}, 2, 1))
        self.assertFalse(_has_next_page({"meta": {"totalPages": 2}}, 2, 1))
        self.assertTrue(_has_next_page({}, 1, 1))
        self.assertFalse(_has_next_page({}, 1, 0))
        self.assertFalse(_has_next_page("not-a-dict", 1, 0))

    def test_iter_paginated_fetches_pages_one_two_three_and_stops_on_false(self):
        calls = []
        payloads = {
            1: {"data": [{"id": 1}], "meta": {"hasNextPage": True}},
            2: {"data": [{"id": 2}], "meta": {"hasNextPage": "true"}},
            3: {"data": [{"id": 3}], "meta": {"hasNextPage": False}},
        }

        def fetch(page, marker):
            calls.append((page, marker))
            return payloads[page]

        client, _ = make_client()
        records = list(client.iter_paginated(fetch, marker="kept"))

        self.assertEqual(records, [{"id": 1}, {"id": 2}, {"id": 3}])
        self.assertEqual(calls, [(1, "kept"), (2, "kept"), (3, "kept")])

    def test_iter_paginated_stops_on_empty_page_without_metadata(self):
        calls = []

        def fetch(page):
            calls.append(page)
            if page == 1:
                return [{"id": 1}]
            return []

        client, _ = make_client()
        records = client.collect_paginated(fetch)

        self.assertEqual(records, [{"id": 1}])
        self.assertEqual(calls, [1, 2])


class MessagingEndpointExtendedTests(unittest.TestCase):
    def test_thread_target_omits_channel_and_posts_exact_body(self):
        client, session = make_client([FakeResponse({"message_uid": "m1"})])

        payload = client.message_booking_guest("Hello", thread_id="thread-9")

        self.assertEqual(payload, {"message_uid": "m1"})
        self.assertEqual(session.calls[0]["method"], "POST")
        self.assertEqual(
            session.calls[0]["url"],
            "https://www.igms.com/api/v1/message-booking-guest",
        )
        self.assertEqual(
            session.calls[0]["json"],
            {"message": "Hello", "thread_id": "thread-9"},
        )

    def test_booking_target_includes_channel_when_set(self):
        client, session = make_client([FakeResponse({"ok": True})])

        client.message_booking_guest("Hello", booking_uid="booking-5", channel="email")

        self.assertEqual(
            session.calls[0]["json"],
            {"message": "Hello", "booking_uid": "booking-5", "channel": "email"},
        )

    def test_message_requires_target_and_non_whitespace_text(self):
        client, _ = make_client()
        with self.assertRaises(ValueError):
            client.message_booking_guest("Hello")
        with self.assertRaises(ValueError):
            client.message_booking_guest("", thread_id="thread-1")
        with self.assertRaises(ValueError):
            client.message_booking_guest(" \t\n", booking_uid="booking-1")

    def test_get_message_status_uses_exact_message_uid_parameter(self):
        client, session = make_client([FakeResponse({"status": "sent"})])

        client.get_message_status("message-uid-1")

        self.assertEqual(
            session.calls[0]["params"],
            {"message_uid": "message-uid-1", "access_token": "token-123"},
        )

    def test_get_all_threads_preserves_camel_case_date_filters(self):
        client, session = make_client([
            FakeResponse({"data": [], "meta": {"hasNextPage": False}})
        ])

        records = client.get_all_threads(
            fromDate="2026-07-24",
            toDate="2026-08-01",
            platformType="airbnb",
        )

        self.assertEqual(records, [])
        self.assertEqual(session.calls[0]["params"], {
            "page": 1,
            "fromDate": "2026-07-24",
            "toDate": "2026-08-01",
            "platformType": "airbnb",
            "access_token": "token-123",
        })

    def test_get_all_threads_fetches_all_pages_with_filters_on_each(self):
        """Regression: a page-2 guest thread must not be dropped. Both page
        calls must carry the camelCase filters and page increments."""
        client, session = make_client([
            FakeResponse({
                "data": [{"threadId": "t1", "messages": [{"messageId": 1}]}],
                "meta": {"hasNextPage": True},
            }),
            FakeResponse({
                "data": [{"threadId": "t2", "messages": [{"messageId": 2}]}],
                "meta": {"hasNextPage": False},
            }),
        ])

        records = client.get_all_threads(fromDate="2026-07-24", toDate="2026-08-01")

        self.assertEqual([r["threadId"] for r in records], ["t1", "t2"])
        self.assertEqual(session.calls[0]["params"]["page"], 1)
        self.assertEqual(session.calls[1]["params"]["page"], 2)
        for call in session.calls:
            self.assertEqual(call["params"]["fromDate"], "2026-07-24")
            self.assertEqual(call["params"]["toDate"], "2026-08-01")


if __name__ == "__main__":
    unittest.main()
