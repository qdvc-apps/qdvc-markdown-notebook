# Transport notes

## Summary

Where there was doubt, we chose the option that fails loudly and early. If you only read one section, read the summary at the top.

## Goals

- Predictable behaviour under load
- A migration path that does not require downtime

## Non-goals

- Rewriting the storage layer
- Supporting the legacy import format

## Design

### Data model

If you only read one section, read the summary at the top. Each decision below was driven by what the team could maintain later.

### Failure modes

| Failure | Detection | Recovery |
| --- | --- | --- |
| Disk full | health check | shed load, alert |
| Slow peer | timeout | retry with backoff |

## Open questions

- How do we handle partial writes?
- Is *eventual* consistency acceptable here?
