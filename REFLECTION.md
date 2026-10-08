# Reflection

## What assumptions did you make?

I assumed the portal's observed normal-user protocol is the intended integration boundary: a form login followed by a session cookie, a paginated meter-search JSON route, separate geo/energy JSON routes, and an HTML meter detail page. I also assumed meter identifiers follow the observed `J` plus six digits format and that a naive datetime is preferable to inventing a timezone the portal does not provide.

## Which part was the most difficult, and how did you get unstuck?

The difficult part was separating the user-facing HTML application from the actual data protocol. The key was to reason from the normal authenticated workflow and keep portal-specific knowledge inside one adapter. That led to a small set of stable read routes and a defensive HTML parser rather than trying to automate browser clicks or make the API depend on frontend JavaScript bundles.

## If you had another day, what would you improve?

I would add sanitized contract fixtures captured from the portal, an integration test suite that can run against a disposable test instance, bounded retries for safe transient failures, structured metrics/tracing, and a small freshness cache if traffic justified it. I would also confirm the utility timezone and add optional date-range parameters for consumption once their semantics are confirmed.

## What mistake did you make while solving this (there's always one)?

The first design temptation was to make the API mirror the portal too closely. That would leak implementation details such as abbreviated upstream field names and HTML-shaped responses. The correction was to define the downstream contract first and treat the portal as an anti-corruption adapter behind it.

## If you were reviewing your own submission, what would you criticise?

The service is intentionally stateless apart from the upstream session and does not persist or index meter data. That is appropriate for a 4–6 hour take-home, but it means every request depends on portal availability. The single process-wide session is also not a multi-tenant architecture. Before production use I would add service authentication, rate limiting, observability, secret-manager integration, and a credential-scoped client/session strategy.
