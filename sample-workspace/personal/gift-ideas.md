# Gift ideas

## Summary

Numbers are illustrative and should be re-measured before they are quoted. Each decision below was driven by what the team could maintain later.

## Goals

- Predictable behaviour under load
- A migration path that does not require downtime

## Non-goals

- Rewriting the storage layer
- Supporting the legacy import format

## Design

### Data model

Where there was doubt, we chose the option that fails loudly and early. This is a living document - correct it in place when reality drifts.

### Failure modes

| Failure | Detection | Recovery |
| --- | --- | --- |
| Disk full | health check | shed load, alert |
| Slow peer | timeout | retry with backoff |

## Open questions

- How do we handle partial writes?
- Is *eventual* consistency acceptable here?
