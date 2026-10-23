# Checkpoints and deployment recovery

## Saved source checkpoints

Use `scripts/checkpoint.py` to save a committed revision as a source archive plus a SHA-256 manifest. Snapshot names cannot be reused, and verification detects archive modification. Credentials, runtime state, logs and virtual environments are excluded. Local archives live in gitignored `checkpoints/`; committed code remains recoverable through Git.

- `pre-upgrade-2026-10-22`: original May 4 revision `2cdc997`, retained for comparison and emergency recovery.
- `api-v2-candidate-2026-10-22`: prior Data API v2/execution update, commit `dfc8cf0`, verified with confirmed live BUY and SELL orders and retained for comparison.
- `cash-controls-2a65e3e-2026-10-22`: approved cash/manual-exit iteration, commit `2a65e3e`, deployed with 105 passing local/VPS tests and healthy service/observers/timer.

A source checkpoint is **not** a record of the server's running version. The server revision must be checked after SSH access is established.

## Deployment procedure

The operator authorized agent-managed VPS deployment, key-based SSH works, and release `2a65e3e` is live. The consistent private pre-activation backup is `/root/polymarket-deploy/checkpoints/before-controls-20261023T023827Z`. Current and previous Python environments are retained. The earlier pre-migration backup remains available separately.

For subsequent deployments:

1. Read actual service status, process command, interpreter, server revision, nonsecret settings and relevant logs. Preserve local server edits and do not print `.env` or credentials.
2. Prepare a separate release directory from the committed source checkpoint and create its own server-native virtual environment. Retain the previous release and environment so rollback does not reinstall dependencies.
3. Validate the new release using read-only readiness checks. Inspect `RECONCILE_ON_START`: enabling it can cause immediate sales on restart.
4. Stop the service before taking a consistent server-local backup of code, `.env`, service configuration and the complete state directory. Keep secret-bearing backups private on the VPS and out of Git.
5. Link the release to the existing live configuration, state and logs; switch the systemd working directory/interpreter to that release. Start one process and inspect submitted versus confirmed fills separately.
6. Record the deployed commit, release directory, checkpoint paths, environment version and validation outcome in deployment notes.

## Rollback rules

The cash/manual-exit iteration also requires preserving `state/controls.sqlite3`. It contains asset pauses, source deferral deadlines and sale attribution identities. The prior `dfc8cf0` code does not enforce those controls. Review active pauses and settings before switching to that older software. The current validated `2a65e3e` baseline retains these controls with automatic external-sale pauses disabled at operator request.

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

## Current recovery baseline

Current baseline: `/root/polymarket-deploy/checkpoints/api-v2-controls-validated-2a65e3e-no-external-pauses`. This retains the verified source archive, systemd configuration and updated validation manifest for the live `2a65e3e` environment, with `MANUAL_EXIT_PROTECTION=0`. Source/runtime identity is recorded separately: this was a configuration change using an existing supported flag, while local defaults and documentation were aligned with it. The original source passed 105 local/VPS tests; the updated local suite passes 106. Fresh successful polling, clean health and the active timer were verified after the policy change. Three natural BUYs have reached filled status since the controls release activated.

The policy-change backup is `/root/polymarket-deploy/checkpoints/before-reentry-policy-20261023T044528Z`, containing a consistent private state snapshot, environment and prior configuration. The earlier pre-activation checkpoint remains `/root/polymarket-deploy/checkpoints/before-controls-20261023T023827Z`. The old recovery bundle without the `-no-external-pauses` suffix is historical and would re-enable the previous automatic-pause policy. Use the current bundle below.

For a future code update, the agent can return to the retained `2a65e3e` release after checking pending orders and database compatibility. The checkpoint's override selects its retained interpreter and approved settings:

```bash
systemctl stop polymarket-bot
cp /root/polymarket-deploy/checkpoints/api-v2-controls-validated-2a65e3e-no-external-pauses/90-release.conf /etc/systemd/system/polymarket-bot.service.d/90-release.conf
systemctl daemon-reload
systemctl start polymarket-bot
systemctl start polymarket-bot-health.service
```

These commands intentionally do not restore `.env`, processed IDs, the order journal or controls database. Retain `MANUAL_EXIT_PROTECTION=0` in the shared `.env` so the separate health process also reflects the current policy. Verify the health unit still points to the intended release, inspect health/logs after switching, and update the deployment manifest. If newer database changes are incompatible, stop and resolve that before running older software.

Use `/root/polymarket-deploy/deployment.json` and `systemctl show polymarket-bot -p ExecStart -p WorkingDirectory` to identify the running release. The active override is `/etc/systemd/system/polymarket-bot.service.d/90-release.conf`. A future code rollback switches that working directory/interpreter to a retained compatible release, keeps live state/log symlinks, reloads systemd and validates logs. Inspect pending/unknown orders before switching, and never start two bot processes.

Previous baseline `dfc8cf0` supports Data API v2 but does not enforce new cash/manual-exit controls. Original `2cdc997` remains available for forensic comparison but should not be blindly restarted with the new state/journal or after old API retirement. A backup restores software/configuration; it cannot reverse trades already executed.

The server also stores `/root/polymarket-deploy/checkpoints/api-v2-validated-dfc8cf0` with its source archive and validation manifest. This older API-compatible baseline predates the new cash/manual controls; prefer the current `2a65e3e` recovery configuration above. The original pre-update backup is separate and retains private configuration/state for diagnosis only.
