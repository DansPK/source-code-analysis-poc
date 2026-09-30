"""M2: both input kinds converge on a Repository with a directory root."""

import base64
import io
import os
import zipfile
from pathlib import Path

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


def test_clone_a_named_branch(tmp_path):
    """Git mode scans the user's current branch, not the default one."""
    origin = tmp_path / "origin"
    origin.mkdir()
    (origin / "app.py").write_text("print('main')\n")
    source = Repo.init(origin)
    source.index.add(["app.py"])
    source.index.commit("initial")
    source.git.checkout("-b", "feature")
    (origin / "feature.py").write_text("print('feature')\n")
    source.index.add(["feature.py"])
    source.index.commit("feature work")
    source.git.checkout("-")

    clone(f"file://{origin}", str(tmp_path / "workspace"), branch="feature")

    assert (tmp_path / "workspace" / "origin" / "feature.py").exists()


# --- uploaded archives -----------------------------------------------------------------


def _zip(files: dict[str, str]) -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return base64.b64encode(buffer.getvalue()).decode()


@pytest.fixture
def upload_settings(tmp_path):
    return Settings(temp_dir=str(tmp_path / "projects"), max_upload_mb=1)


def test_archive_unpacks_into_the_workspace(upload_settings, tmp_path):
    archive = _zip({"app.py": "x = 1\n", "routes/search.py": "y = 2\n"})

    repo = load_source(None, None, upload_settings, archive=archive)

    assert repo.root.startswith(str(tmp_path / "projects" / "uploads"))
    assert (Path(repo.root) / "routes" / "search.py").read_text() == "y = 2\n"


def test_the_same_upload_reuses_its_extraction(upload_settings):
    """A follow-up question sends the project again; it must not pile up copies."""
    archive = _zip({"app.py": "x = 1\n"})
    first = load_source(None, None, upload_settings, archive=archive)
    second = load_source(None, None, upload_settings, archive=archive)
    assert first.root == second.root


def test_subpath_narrows_an_archive_to_one_file(upload_settings):
    archive = _zip({"app.py": "x = 1\n", "routes/search.py": "y = 2\n"})

    repo = load_source(None, None, upload_settings, archive=archive, subpath="routes/search.py")

    assert repo.root.endswith("routes") and repo.single_file == "search.py"


def test_subpath_cannot_leave_the_project(upload_settings):
    with pytest.raises(SourceError, match="outside the project"):
        load_source(None, None, upload_settings, archive=_zip({"a.py": ""}), subpath="../../etc")


@pytest.mark.parametrize("name", ["../escape.py", "/etc/escape.py"])
def test_zip_slip_is_refused(upload_settings, tmp_path, name):
    with pytest.raises(SourceError, match="Unsafe path"):
        load_source(None, None, upload_settings, archive=_zip({name: "boom"}))
    assert not list(tmp_path.rglob("escape.py"))


def test_oversized_upload_is_refused(upload_settings):
    big = base64.b64encode(os.urandom(2 * 1024 * 1024)).decode()
    with pytest.raises(SourceError, match="at most 1 MB"):
        load_source(None, None, upload_settings, archive=big)


@pytest.mark.parametrize("archive", ["not base64!", base64.b64encode(b"not a zip").decode()])
def test_malformed_upload_is_reported_clearly(upload_settings, archive):
    with pytest.raises(SourceError, match="not"):
        load_source(None, None, upload_settings, archive=archive)
