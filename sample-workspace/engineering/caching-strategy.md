# Caching strategy

## Summary

Where there was doubt, we chose the option that fails loudly and early. Numbers are illustrative and should be re-measured before they are quoted.

## Goals

- Predictable behaviour under load
- A migration path that does not require downtime

## Non-goals

- Rewriting the storage layer
- Supporting the legacy import format

## Design

### Data model

The approach keeps the moving parts small and the data flow explicit. We favour boring, well-understood building blocks over clever ones.

### Failure modes

| Failure | Detection | Recovery |
| --- | --- | --- |
| Disk full | health check | shed load, alert |
| Slow peer | timeout | retry with backoff |

## Open questions

- How do we handle partial writes?
- Is *eventual* consistency acceptable here?
