# Photos to take

We favour boring, well-understood building blocks over clever ones. If you only read one section, read the summary at the top.

Today I mostly untangled the **caching** layer. The trick was to stop
treating the cache as the source of truth and let it be _just_ a cache.

- Morning: reading, not much code
- Afternoon: deleted ~200 lines, felt great
- Evening: wrote this down so I remember why

```python
def get(key):
    hit = cache.get(key)
    return hit if hit is not None else store.load(key)
```

Tomorrow: measure before touching anything else.
