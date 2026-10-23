# Checkpoints and deployment recovery

## Saved source checkpoints

Use `scripts/checkpoint.py` to save a committed revision as a source archive plus a SHA-256 manifest. Snapshot names cannot be reused, and verification detects archive modification. Credentials, runtime state, logs and virtual environments are excluded. Local archives live in gitignored `checkpoints/`; committed code remains recoverable through Git.

- `pre-upgrade-2026-10-22`: original May 4 revision `2cdc997`, retained for comparison and emergency recovery.
- A separate checkpoint captures the committed Data API v2/execution update before its first server deployment.

A source checkpoint is **not** a record of the server's running version. The server revision must be checked after SSH access is established.

## Deployment procedure

The operator authorized agent-managed VPS deployment in this conversation. SSH currently requires a one-time key enrollment. The server has not been changed by the failed SSH access test.

After access works:

1. Read actual service status, process command, interpreter, server revision, nonsecret settings and relevant logs. Preserve local server edits and do not print `.env` or credentials.
2. Prepare a separate release directory from the committed source checkpoint and create its own server-native virtual environment. Retain the previous release and environment so rollback does not reinstall dependencies.
3. Validate the new release using read-only readiness checks. Inspect `RECONCILE_ON_START`: enabling it can cause immediate sales on restart.
4. Stop the service before taking a consistent server-local backup of code, `.env`, service configuration and the complete state directory. Keep secret-bearing backups private on the VPS and out of Git.
5. Link the release to the existing live configuration, state and logs; switch the systemd working directory/interpreter to that release. Start one process and inspect submitted versus confirmed fills separately.
6. Record the deployed commit, release directory, checkpoint paths, environment version and validation outcome in deployment notes.

## Rollback rules

Roll back **code and dependencies**, preserving the latest live processed-trade state and order journal. Never blindly restore an old state snapshot after live trading: replayed source trades could create duplicate purchases. Do not start old code that cannot interpret the current state/journal while an order is pending or uncertain.

The May 4 code uses the retiring Data API v1 routes. It is not a durable fallback after their announced October 24 retirement. After the first validated v2 deployment, use an API-compatible v2 release as the normal rollback baseline. If compatibility or pending-order safety is uncertain, leave trading stopped while investigating rather than automatically starting an incompatible release.

Backups preserve configuration for diagnosis, but credentials and wallet identity must not be rolled back blindly. A code rollback also cannot reverse trades that already executed.

## Commands used by the agent

```bash
python3 scripts/checkpoint.py create NAME --ref COMMIT
python3 scripts/checkpoint.py verify checkpoints/NAME
python3 scripts/checkpoint.py list
```

The operator does not need to edit application code or run these routinely; they document how checkpoints are generated and verified.
