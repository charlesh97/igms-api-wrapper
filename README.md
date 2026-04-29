# igms-api-wrapper

Python wrapper and CLI for the [iGMS](https://igms.com) property management API.

## Install

```bash
pip install -e .
```

## Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Environment variables:

| Variable | Description |
|----------|-------------|
| `IGMS_CLIENT_ID` | OAuth client ID |
| `IGMS_CLIENT_SECRET` | OAuth client secret |
| `IGMS_REDIRECT_URI` | OAuth redirect URI |
| `IGMS_SCOPE` | API scopes (default: `listings`) |
| `IGMS_ACCESS_TOKEN` | Access token (from OAuth exchange) |

## CLI Usage

```bash
# OAuth flow
igms generate-secret
igms auth-url
igms exchange --code 'AUTH_CODE'

# Fetch data
igms properties
igms listings
igms bookings --filters '{"booking_status":"accepted"}'
igms calendar --property-uid 'UID' --from-date 2026-04-29 --to-date 2026-05-06
igms threads

# Name lookup
igms find-property 'Frosty Pines'
igms find-listing 'Close to DC'

# Portfolio status
igms status
igms status --days 14 --json

# Raw API
igms api --path /api/v1/bookings --params '{"page":1}'
```

## Python Usage

```python
from igms_wrapper import IGMSClient, build_portfolio_status, format_portfolio_status_text

client = IGMSClient.from_env()

# Direct API calls
properties = client.get_all_properties()
bookings = client.get_all_bookings(booking_status="accepted")
calendar = client.get_calendar("PROPERTY_UID", "2026-04-29", "2026-05-06")

# Name lookup
match = client.find_property_by_name("Frosty Pines")

# Portfolio status summary
status = build_portfolio_status(client, days=7)
print(format_portfolio_status_text(status))
```

## Tests

```bash
python -m pytest tests/ -v
```
