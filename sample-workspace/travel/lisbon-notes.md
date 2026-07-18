# Lisbon notes

## Summary

Numbers are illustrative and should be re-measured before they are quoted. Notes here are deliberately short; link out rather than duplicate.

## Goals

- Predictable behaviour under load
- A migration path that does not require downtime

## Non-goals

- Rewriting the storage layer
- Supporting the legacy import format

## Design

### Data model

The approach keeps the moving parts small and the data flow explicit. Each decision below was driven by what the team could maintain later.

### Failure modes

| Failure | Detection | Recovery |
| --- | --- | --- |
| Disk full | health check | shed load, alert |
| Slow peer | timeout | retry with backoff |

## Open questions

- How do we handle partial writes?
- Is *eventual* consistency acceptable here?
