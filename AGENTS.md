# Repository context

Start a new conversation by reading [the session handoff](docs/SESSION_HANDOFF.md), then [project status](docs/PROJECT_STATUS.md). Use Git history for completed work; repository HEAD and the running VPS release can differ.

- Save completed code and documentation changes to GitHub. Keep credentials, raw logs, runtime state and private backups out of Git.
- The operator authorizes agent-managed SSH deployments within the agreed scope. Confirm proposed new trading policies before activation unless the operator has already explicitly authorized them.
- Current manual-sale policy permits fresh eligible target BUYs after an external sale. Preserve this preference during updates and recovery.
- Before live changes, inspect the actual service configuration and follow [deployment/recovery notes](docs/CHECKPOINTS.md). Preserve the latest processed IDs, order journal and controls database.
- Update the handoff and relevant operational docs when deployment, decisions, validation or outstanding work changes. Record observation times; saved health results are historical snapshots.
