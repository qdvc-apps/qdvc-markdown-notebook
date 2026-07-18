# Plant care

## Summary

The approach keeps the moving parts small and the data flow explicit. We favour boring, well-understood building blocks over clever ones.

## Goals

- Predictable behaviour under load
- A migration path that does not require downtime

## Non-goals

- Rewriting the storage layer
- Supporting the legacy import format

## Design

### Data model

This is a living document - correct it in place when reality drifts. Where there was doubt, we chose the option that fails loudly and early.

### Failure modes

| Failure | Detection | Recovery |
| --- | --- | --- |
| Disk full | health check | shed load, alert |
| Slow peer | timeout | retry with backoff |

## Open questions

- How do we handle partial writes?
- Is *eventual* consistency acceptable here?
