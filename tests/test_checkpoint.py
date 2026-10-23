"""Source checkpoints exclude runtime data and detect tampering."""
import importlib.util
from pathlib import Path
import subprocess
import tarfile
import pytest

spec = importlib.util.spec_from_file_location("checkpoint_script", Path(__file__).parents[1] / "scripts" / "checkpoint.py")
checkpoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checkpoint)


@pytest.fixture
def repo(tmp_path):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
    git("init")
    git("config", "user.name", "Checkpoint test")
    git("config", "user.email", "test@example.invalid")
    (tmp_path / "main.py").write_text("print('checkpoint')\n")
    (tmp_path / "requirements.txt").write_text("requests==2.34.2\n")
    git("add", "main.py", "requirements.txt")
    git("-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "commit", "-m", "Fixture")
    (tmp_path / ".env").write_text("SECRET=never-archive\n")
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "seen_trades.json").write_text("{}")
    return tmp_path


def test_checkpoint_archives_committed_code_only(repo):
    destination = checkpoint.create_checkpoint("before-update", root=repo)
    manifest = checkpoint.verify_checkpoint(destination)
    assert manifest["local_worktree_dirty"]
    with tarfile.open(destination / "source.tar.gz") as handle:
        assert set(handle.getnames()) == {"main.py", "requirements.txt"}
    assert (repo / ".env").read_text() == "SECRET=never-archive\n"


def test_tampered_archive_is_rejected(repo):
    destination = checkpoint.create_checkpoint("before-update", root=repo)
    with (destination / "source.tar.gz").open("ab") as handle:
        handle.write(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        checkpoint.verify_checkpoint(destination)


def test_checkpoint_cannot_overwrite_existing_snapshot(repo):
    checkpoint.create_checkpoint("before-update", root=repo)
    with pytest.raises(FileExistsError):
        checkpoint.create_checkpoint("before-update", root=repo)


def test_checkpoint_rejects_path_traversal(repo):
    with pytest.raises(ValueError):
        checkpoint.create_checkpoint("../outside", root=repo)
