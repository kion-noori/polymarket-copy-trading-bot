"""Create and verify source-only Git checkpoints without touching live trading state."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str, root: Path = ROOT) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def create_checkpoint(name: str, ref: str = "HEAD", *, root: Path = ROOT) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", name):
        raise ValueError("Checkpoint name must use letters, digits, dots, dashes or underscores")
    commit = git("rev-parse", "--verify", f"{ref}^{{commit}}", root=root)
    tracked = git("ls-tree", "-r", "--name-only", commit, root=root).splitlines()
    forbidden = [name for name in tracked if name == ".env" or name.startswith(("state/", "logs/", ".venv/", ".ssh/"))]
    if forbidden:
        raise ValueError("Refusing to archive a commit containing secrets or runtime state")
    destination = root / "checkpoints" / name
    destination.mkdir(parents=True, exist_ok=False)
    archive = destination / "source.tar.gz"
    git("archive", "--format=tar.gz", f"--output={archive}", commit, root=root)
    try:
        requirements = git("show", f"{commit}:requirements.txt", root=root)
    except subprocess.CalledProcessError:
        requirements = ""
    manifest = {"name": name, "commit": commit, "created_at": datetime.now(timezone.utc).isoformat(),
                "source_sha256": digest(archive), "requirements": requirements,
                "local_worktree_dirty": bool(git("status", "--porcelain", root=root)),
                "scope": "Committed source only. Credentials, live state, logs and virtual environments are excluded.",
                "rollback": "Deploy in a separate release directory. Keep current trade state and pending-order journal. Never restore old processed state after live trades."}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return destination


def verify_checkpoint(path: Path) -> dict:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    archive = path / "source.tar.gz"
    if digest(archive) != manifest["source_sha256"]:
        raise ValueError("Checkpoint archive checksum does not match")
    with tarfile.open(archive) as handle:
        for member in handle.getmembers():
            parts = Path(member.name).parts
            if member.name.startswith("/") or ".." in parts or member.issym() or member.islnk():
                raise ValueError("Checkpoint contains unsafe archive paths or links")
            if parts and (parts[0] in ("state", "logs", ".venv", ".ssh") or member.name == ".env"):
                raise ValueError("Checkpoint contains excluded runtime data")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser("create")
    create.add_argument("name")
    create.add_argument("--ref", default="HEAD")
    verify = actions.add_parser("verify")
    verify.add_argument("path", type=Path)
    actions.add_parser("list")
    args = parser.parse_args()
    try:
        if args.action == "create":
            path = create_checkpoint(args.name, args.ref)
            print(f"Created {path} from {verify_checkpoint(path)['commit']}")
        elif args.action == "verify":
            print(json.dumps(verify_checkpoint(args.path), indent=2))
        else:
            for path in sorted((ROOT / "checkpoints").glob("*/manifest.json")):
                print(f"{path.parent.name}: {json.loads(path.read_text())['commit']}")
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Checkpoint failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
