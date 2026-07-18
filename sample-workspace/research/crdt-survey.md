# CRDT survey

## Summary

We favour boring, well-understood building blocks over clever ones. Each decision below was driven by what the team could maintain later.

## Goals

- Predictable behaviour under load
- A migration path that does not require downtime

## Non-goals

- Rewriting the storage layer
- Supporting the legacy import format

## Design

### Data model

Notes here are deliberately short; link out rather than duplicate. The approach keeps the moving parts small and the data flow explicit.

### Failure modes

| Failure | Detection | Recovery |
| --- | --- | --- |
| Disk full | health check | shed load, alert |
| Slow peer | timeout | retry with backoff |

## Open questions

- How do we handle partial writes?
- Is *eventual* consistency acceptable here?
