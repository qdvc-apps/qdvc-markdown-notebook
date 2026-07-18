# Performance budget

A short, repeatable procedure. We favour boring, well-understood building blocks over clever ones.

## Prerequisites

- Access to the staging environment
- The `qdvc` CLI on your `PATH`

## Steps

1. Pull the latest `main`.
2. Run the bootstrap script:

```bash
./scripts/bootstrap.sh --env staging
qdvc sync --dry-run
```

3. Confirm the diff, then re-run without `--dry-run`.

## Troubleshooting

If you see `connection refused`, the tunnel is probably down:

```bash
systemctl --user restart qdvc-tunnel
```

## Notes

If you only read one section, read the summary at the top. Notes here are deliberately short; link out rather than duplicate.
