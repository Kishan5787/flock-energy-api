# Urja Meter Ops protocol notes

## Discovery summary

The portal is a server-rendered SvelteKit application with JSON data routes used by the normal authenticated UI. The service below uses only read paths and the normal login flow; it does not probe or submit write operations.

## Authentication

- `GET /login` serves the sign-in page.
- Login is a form submission: `POST /login` with URL-encoded `email` and `password` fields.
- A successful login redirects to `/meters` and establishes an HTTP session cookie.
- No bearer token or CSRF field is required by the observed login form.
- An unauthenticated data/page request redirects to `/login`; stale sessions can also produce `401`/`403`.
- The adapter treats either case as an expired session, logs in once again, and retries the original idempotent request.
- Credentials are loaded from environment variables and are never returned to API consumers.

## Data routes

| Method | Route | Observed shape / purpose |
|---|---|---|
| `GET` | `/portal/meters/search?q={query}&page={page}` | JSON `{data, total, page, pageSize}`; 20 records per page at discovery time. `q` accepts meter ID or serial number. |
| `GET` | `/portal/meters/{meterId}/geo` | JSON `{data: {latitude, longitude}}`; coordinates arrive as strings. |
| `GET` | `/portal/meters/{meterId}/energy` | JSON `{data: [{timestamp, kwh, kvah, voltR}]}`. |
| `GET` | `/meters/{meterId}` | Server-rendered HTML containing nameplate fields and a hierarchy breadcrumb. |

The visible meter listing contained 403 meters during discovery, with 20 records per page. The exact count is intentionally not baked into the API because it is portal state, not an application constant.

## Data quirks and normalization

- Upstream JSON uses abbreviated/camel-case keys such as `meterId`, `serialNo`, `dtCode`, and `voltR`.
- Numeric values are represented as strings and are converted to JSON numbers at the API boundary.
- Consumption timestamps use `DD/MM/YYYY HH:mm` and arrive at 30-minute intervals. They are returned as ISO-8601 datetime strings by Pydantic.
- The upstream payload does not specify a timezone. The API therefore does not invent one; the resulting datetime is intentionally timezone-naive.
- Meter hierarchy is rendered as breadcrumb text. The parser identifies hierarchy levels by their stable code prefixes (`Z-`, `C-`, `D-`, `SD-`, `SS-`, `F-`, `DT-`) instead of relying on fixed breadcrumb positions.
- Missing fields become `null`.
- A malformed individual consumption row is skipped and logged so one bad reading does not invalidate the entire series.

## API boundary

The clean API intentionally hides portal paths, abbreviated field names, HTML, and session cookies. It exposes typed JSON under `/api/v1` and returns controlled `502`/`503` errors for upstream failures rather than leaking upstream HTML or returning fabricated empty data.

## Operational boundaries

The adapter is read-only. It does not scrape JavaScript bundles as a runtime dependency, perform mutations, or expose the upstream session cookie. The API should be treated as a thin integration layer rather than a replacement database.
