# Experiment log

## Summary

Notes here are deliberately short; link out rather than duplicate. We favour boring, well-understood building blocks over clever ones.

## Goals

- Predictable behaviour under load
- A migration path that does not require downtime

## Non-goals

- Rewriting the storage layer
- Supporting the legacy import format

## Design

### Data model

If you only read one section, read the summary at the top. We favour boring, well-understood building blocks over clever ones.

### Failure modes

| Failure | Detection | Recovery |
| --- | --- | --- |
| Disk full | health check | shed load, alert |
| Slow peer | timeout | retry with backoff |

## Open questions

- How do we handle partial writes?
- Is *eventual* consistency acceptable here?
