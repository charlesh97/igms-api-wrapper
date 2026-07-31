# iGMS API Reference

Pulled from https://www.igms.com/docs/airgms-api/ on 2026-07-31. Raw HTML cached in this directory.

## Endpoint Index

| Method | Verb | URL | Scope |
|--------|------|-----|-------|
| v1/get-properties | GET | `https://www.igms.com/api/v1/property` | `-` |
| v1/get-property | GET | `https://www.igms.com/api/v1/property/{propertyUid}` | `-` |
| v1/company | GET | `https://www.igms.com/api/v1/company` | `-` |
| v1/listings | GET | `https://www.igms.com/api/v1/listings` | `-` |
| v1/bookings | GET | `https://www.igms.com/api/v1/bookings` | `-` |
| v1/guests | GET | `https://www.igms.com/api/v1/guests` | `messaging` |
| v1/hosts | GET | `https://www.igms.com/api/v1/hosts` | `-` |
| v1/tasks | GET | `https://www.igms.com/api/v1/tasks` | `tasks` |
| v1/get-calendar-data | GET | `https://www.igms.com/api/v1/get-calendar-data` | `-` |
| v1/propose-calendar-batch | POST | `https://www.igms.com/api/v1/calendar-batch` | `pricing` |
| v1/set-calendar-batch | POST | `https://www.igms.com/api/v1/set-calendar-batch` | `calendar` |
| v1/book-property | POST | `https://www.igms.com/api/v1/book-property` | `direct` |
| v2/cancel-booking | POST | `https://www.igms.com/api/v2/cancel-booking` | `direct` |
| v2/accept-reservation | POST | `https://www.igms.com/api/v2/accept-reservation` | `direct` |
| v2/decline-reservation | POST | `https://www.igms.com/api/v2/decline-reservation` | `direct` |
| v2/set-property-calendar-control | POST | `https://www.igms.com/api/v2/set-property-calendar-control` | `pricing` |
| v2/set-property-calendar-availability | POST | `https://www.igms.com/api/v2/set-property-calendar-availability` | `availability` |
| v1/get-request-status | GET | `https://www.igms.com/api/v1/get-request-status` | `-` |
| v1/message-booking-guest | POST | `https://www.igms.com/api/v1/message-booking-guest` | `messaging` |
| v1/message-status | GET | `https://www.igms.com/api/v1/message-status` | `messaging` |
| v1/get-threads | GET | `https://www.igms.com/api/v1/get-threads` | `messaging` |

---
## v1/get-properties

- **HTTP**: `GET`
- **URL**: `https://www.igms.com/api/v1/property`
- **Description**: Get properties data

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| page | int | optional | 1 | Page number for pagination |

---
## v1/get-property

- **HTTP**: `GET`
- **URL**: `https://www.igms.com/api/v1/property/{propertyUid}`
- **Description**: Get information about specific property

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| propertyUid | string | required | none | Url parameter |

---
## v1/company

- **HTTP**: `GET`
- **URL**: `https://www.igms.com/api/v1/company`
- **Description**: This method shows common info of the current company.

---
## v1/listings

- **HTTP**: `GET`
- **URL**: `https://www.igms.com/api/v1/listings`
- **Description**: List of listings managed by the company

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| listing_uids | string | optional | none | List of comma separated listing UIDs |
| listing_status | string | optional | none | One of available listing statuses (see the corresponding filters section) |
| property_status | string | optional | none | One of available property statuses (see the corresponding filters section) |
| platform_type | string | optional | none | List of comma separated platform types (see the corresponding filters section). This filter returns listings related to one of mentioned platform types |
| page | int | optional | 1 | Page number for pagination |

---
## v1/bookings

- **HTTP**: `GET`
- **URL**: `https://www.igms.com/api/v1/bookings`
- **Description**: List of active bookings

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| booking_uids | string | optional | none | List of comma separated booking UIDs |
| booking_status | string | optional | none | One of available booking statuses (see the corresponding filters section) |
| platform_type | string | optional | none | List of comma separated platform types (see the corresponding filters section). This filter returns bookings related to one of mentioned platform types |
| from_date | string | optional | none | Hide bookings ended before this date |
| to_date | string | optional | none | Hide bookings which will be started after this date |
| from_created_date | string | optional | none | Hide bookings which created on iGMS before this date |
| to_created_date | string | optional | none | Hide bookings which created on iGMS after this date |
| from_updated_date | string | optional | none | Hide bookings which updated before this date |
| to_updated_date | string | optional | none | Hide bookings which updated after this date |
| from_booked_date | string | optional | none | Hide bookings which are booked before this date |
| to_booked_date | string | optional | none | Hide bookings which are booked after this date |
| order_by_created_dttm | bool | optional | none | When true, results are ordered by created_dttm DESC (newest first) |
| page | int | optional | 1 | Page number for pagination |

---
## v1/guests

- **HTTP**: `GET`
- **URL**: `https://www.igms.com/api/v1/guests`
- **Scope**: `messaging`
- **Description**: List of all guests

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| guest_uids | string | optional | none | List of comma separated guest UIDs |
| platform_type | string | optional | none | List of comma separated platform types (see the corresponding filters section). This filter returns guests related to one of mentioned platform types |
| page | int | optional | 1 | Page number for pagination |

---
## v1/hosts

- **HTTP**: `GET`
- **URL**: `https://www.igms.com/api/v1/hosts`
- **Description**: List of all hosts

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| host_uids | string | optional | none | List of comma separated host UIDs |
| platform_type | string | optional | none | List of comma separated platform types (see the corresponding filters section). This filter returns hosts related to one of mentioned platform types |
| page | int | optional | 1 | Page number for pagination |

---
## v1/tasks

- **HTTP**: `GET`
- **URL**: `https://www.igms.com/api/v1/tasks`
- **Scope**: `tasks`
- **Description**: List of active tasks

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| task_uids | string | optional | none | List of comma separated task UIDs |
| property_uids | string | optional | none | List of comma separated property UIDs |
| from_date | string | optional | none | Hide tasks which was started before this date |
| to_date | string | optional | none | Hide tasks which will be started after this date |
| page | int | optional | 1 | Page number for pagination |

---
## v1/get-calendar-data

- **HTTP**: `GET`
- **URL**: `https://www.igms.com/api/v1/get-calendar-data`
- **Description**: Returns the property's calendar data for the period (no more than a year)

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| property_uid | string | required | none | UID of property. |
| from_date | string | required | none | YYYY-MM-DD First date of the period. |
| to_date | string | required | none | YYYY-MM-DD Last date of the period. |

---
## v1/propose-calendar-batch

- **HTTP**: `POST`
- **URL**: `https://www.igms.com/api/v1/calendar-batch`
- **Scope**: `pricing`
- **Description**: Set property's calendar data for separate days. Data will be applied only if user's property setting allows it, otherwise data will be saved for further user's review.

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| days | array | required | none | Array of BatchDayDto objects. |
| property_uid | string | required | none | UID of property. |
| is_user_action | bool | optional | false | Is request was caused by user action |

**Request sample:**

```json
{
    "property_uid": "e3ddcd1a-0e3e-4649-91be-c59d7b56",
    "days":[
        {
            "date": "2021-02-08",
            "currency": "CAD",
            "price": 52,
            "min_stay": 2
        },
        {
            "date": "2021-02-09",
            "currency": "CAD",
            "price": 52,
            "min_stay": 1,
            "is_available": 0
        },
        {
            "date": "2021-02-10",
            "currency": "CAD",
            "price": 50,
            "min_stay": 4
        }
    ],
    "is_user_action": false
}
```

---
## v1/set-calendar-batch

- **HTTP**: `POST`
- **URL**: `https://www.igms.com/api/v1/set-calendar-batch`
- **Scope**: `calendar`
- **Description**: Changes the property's calendar data for separate days

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| property_uid | string | required | none | UID of property. |
| days | object | required | none | Array of BatchDay objects. |

**Request sample:**

```json
{
    "property_uid":"e3ddcd1a-0e3e-4649-91be-c59d7b56",
    "days":[
        {
            "date": "2021-02-14",
            "currency": "CAD",
            "price": 50,
            "min_stay": 3,
            "is_available": 0,
            "notes": "Blocked"
        },
        {
            "date": "2021-02-15",
            "price": 50,
            "min_stay": 3,
            "is_available": 1
        },
        {
            "date": "2021-02-16",
            "currency": "CAD",
            "price": 50,
            "min_stay": 3
        }
    ]
}
```

---
## v1/book-property

- **HTTP**: `POST`
- **URL**: `https://www.igms.com/api/v1/book-property`
- **Scope**: `direct`
- **Description**: Create or update (by reservation_code) existing booking (airgms platform only).

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| property_uid | string | required | none | UID of property. |
| checkin_date | string | required | none | YYYY-MM-DD Check-in date. |
| checkout_date | string | required | none | YYYY-MM-DD Checkout date. |
| guest_name | string | required | none | Guest name. |
| guests | int | required | none | Number of guests. |
| price_total | float | required | none | Total payout. |
| currency | string | required | none | Currency code (3 symbols). |
| description | string | optional | none | Additional information. |
| reservation_code | string | optional | none | Reservation code to update existing booking |

---
## v2/cancel-booking

- **HTTP**: `POST`
- **URL**: `https://www.igms.com/api/v2/cancel-booking`
- **Scope**: `direct`
- **Description**: Cancel an existing booking by reservation_code (airgms platform only).

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| reservation_code | string | required | none | Reservation code to update existing booking |

---
## v2/accept-reservation

- **HTTP**: `POST`
- **URL**: `https://www.igms.com/api/v2/accept-reservation`
- **Scope**: `direct`
- **Description**: Accept an incoming reservation request by reservation_code (airgms platform only).

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| reservation_code | string | required | none | Reservation code |

---
## v2/decline-reservation

- **HTTP**: `POST`
- **URL**: `https://www.igms.com/api/v2/decline-reservation`
- **Scope**: `direct`
- **Description**: Decline an incoming reservation request by reservation_code (airgms platform only).

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| reservation_code | string | required | none | Reservation code |

---
## v2/set-property-calendar-control

- **HTTP**: `POST`
- **URL**: `https://www.igms.com/api/v2/set-property-calendar-control`
- **Scope**: `pricing`
- **Description**: Enable or disable calendar control for pricing management app by property UID.

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| property_uid | string | required | none | UID of property. |
| calendar_control_allowed | bool | required | none | Enable or disable control |

---
## v2/set-property-calendar-availability

- **HTTP**: `POST`
- **URL**: `https://www.igms.com/api/v2/set-property-calendar-availability`
- **Scope**: `availability`
- **Description**: Block or unblock specific dates by property UID.

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| property_uid | string | required | none | UID of property. |
| start_date | string | required | none | YYYY-MM-DD Start of the updated period. |
| end_date | string | required | none | YYYY-MM-DD End of the updated period. |
| is_available | int | required | none | Is property available (1) or not (0). |

**Request sample:**

```json
{
    "property_uid": "e3ddcd1a-0e3e-4649-91be-c59d7b50",
    "start_date": "2023-05-04",
    "end_date": "2023-05-09",
    "is_available": 1
}
```

---
## v1/get-request-status

- **HTTP**: `GET`
- **URL**: `https://www.igms.com/api/v1/get-request-status`
- **Description**: Returns status of the request sent before with another endpoint.

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| request_uid | string | required | none | UID of the request |

---
## v1/message-booking-guest

- **HTTP**: `POST`
- **URL**: `https://www.igms.com/api/v1/message-booking-guest`
- **Scope**: `messaging`
- **Description**: Sends message to the main guest of a booking with using different available channels.

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| message | string | required | none | Message (it's length may be limited for certain channel types). |
| thread_id | string | optional | none | Thread id (required without thread_uid and booking_uid). |
| booking_uid | string | optional | none | UID of a booking (required without thread_uid). |
| channel | string | optional | platform | Channel type (see the corresponding filters section). Use 'email' for direct bookings, 'platform' for other platforms. |

---
## v1/message-status

- **HTTP**: `GET`
- **URL**: `https://www.igms.com/api/v1/message-status`
- **Scope**: `messaging`
- **Description**: Returns status of the message sent with the message-booking-guest method.

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| message_uid | string | required | none | UID of the message |

---
## v1/get-threads

- **HTTP**: `GET`
- **URL**: `https://www.igms.com/api/v1/get-threads`
- **Scope**: `messaging`
- **Description**: Retrieve threads with their messages.

**Params:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| bookingsUids | string | optional | none | List of comma separated booking UIDs |
| threadIds | string | optional | none | List of comma separated thread Ids |
| fromDate | string | optional | none | YYYY-MM-DD Start of the updated period. If only this date is provided, the toDate will be automatically set. |
| toDate | string | optional | none | YYYY-MM-DD End of the updated period. If only this date is provided, the fromDate will be automatically set. |
| page | int | optional | 1 | Page number for pagination |

**Request sample:**

```json
{
  "fromDate": "2024-11-19",
  "toDate": "2024-11-20",
  "page": 1
}
```
