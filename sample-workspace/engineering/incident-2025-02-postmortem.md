# Incident 2025-02 postmortem

A short, repeatable procedure. Each decision below was driven by what the team could maintain later.

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

The approach keeps the moving parts small and the data flow explicit. Each decision below was driven by what the team could maintain later.
