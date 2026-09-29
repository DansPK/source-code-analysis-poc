"""M2: both input kinds converge on a Repository with a directory root."""

import pytest
from git import Repo

from app.config.settings import Settings
from app.source import SourceError
from app.source.git_loader import _workspace, clone
from app.source.loader import load_source

SAMPLE = "tests/vulnerable_samples/flask_app"


def test_local_directory():
    repo = load_source(None, SAMPLE, Settings())
    assert repo.root.endswith("vulnerable_samples/flask_app")
    assert repo.single_file is None and repo.origin is None


def test_local_file_roots_at_its_directory():
    repo = load_source(None, f"{SAMPLE}/routes/search.py", Settings())
    assert repo.root.endswith("flask_app/routes")
    assert repo.single_file == "search.py"


def test_missing_path_is_reported_clearly():
    with pytest.raises(SourceError, match="does not exist"):
        load_source(None, "/no/such/place", Settings())


def test_no_input_at_all():
    with pytest.raises(SourceError):
        load_source(None, None, Settings())


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/example/vulnerable-app.git", "vulnerable-app"),
        ("https://github.com/example/vulnerable-app/", "vulnerable-app"),
        ("git@github.com:example/app.git", "app"),
    ],
)
def test_workspace_name_derived_from_url(url, expected, tmp_path):
    assert _workspace(url, str(tmp_path)).name == expected


def test_clone_from_a_real_repository(tmp_path):
    """Clones a repository created on disk, so the test needs no network."""
    origin = tmp_path / "origin"
    origin.mkdir()
    (origin / "app.py").write_text("print('hi')\n")
    source = Repo.init(origin)
    source.index.add(["app.py"])
    source.index.commit("initial")

    repo = clone(f"file://{origin}", str(tmp_path / "workspace"))

    assert repo.origin.startswith("file://")
    assert (tmp_path / "workspace" / "origin" / "app.py").exists()


def test_clone_failure_is_reported_clearly(tmp_path):
    with pytest.raises(SourceError, match="Could not clone"):
        clone(f"file://{tmp_path}/nonexistent", str(tmp_path / "workspace"))
