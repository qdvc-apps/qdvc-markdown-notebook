# Travel ideas

A short, repeatable procedure. The approach keeps the moving parts small and the data flow explicit.

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

Notes here are deliberately short; link out rather than duplicate. We favour boring, well-understood building blocks over clever ones.
