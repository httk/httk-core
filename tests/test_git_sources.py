"""Git URI sources: parsing, fetching, caching and installed members."""

import json
import logging
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from httk.core import git_sources
from httk.core.git_sources import (
    GitUri,
    cached_git_checkout,
    fetch_git_checkout,
    install_git_member,
    installed_git_member,
    installed_git_members,
    parse_git_uri,
    resolve_installed_name,
    uninstall_git_members,
)
from httk.core.userdirs import data_home

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not available")

_MARKER = "marker.toml"


@pytest.fixture(autouse=True)
def isolated_homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTK_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("HTTK_CONFIG_HOME", str(tmp_path / "config"))


def _git(cwd: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.test", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repository(root: Path, members: dict[str, str]) -> tuple[Path, str]:
    """Create a repository whose *members* map subdir ("" = root) to short name."""

    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    for subdir, name in members.items():
        directory = root / subdir if subdir else root
        directory.mkdir(parents=True, exist_ok=True)
        (directory / _MARKER).write_text(name, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "one")
    return root, _git(root, "rev-parse", "HEAD")


def _commit(root: Path, message: str) -> str:
    (root / "CHANGES").write_text(message, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _names(member: Path) -> tuple[str]:
    return ((member / _MARKER).read_text(encoding="utf-8"),)


def _install(uri: str) -> git_sources.InstalledGitMember:
    return install_git_member("things", uri, _MARKER, _names)


def _refuse(*arguments: object, **options: object) -> None:
    raise AssertionError("git must not run")


def test_parse_canonicalizes() -> None:
    parsed = parse_git_uri("git+HTTPS://GitHub.COM/Org/Repo/@ABCDEF0123456789ABCDEF0123456789ABCDEF01#sub/")
    assert parsed == GitUri("git+https://github.com/Org/Repo", "abcdef0123456789abcdef0123456789abcdef01", "sub")
    assert parsed.pinned
    assert str(parsed) == "git+https://github.com/Org/Repo@abcdef0123456789abcdef0123456789abcdef01#sub"
    kept = parse_git_uri("git+https://example.test/org/repo.git@feature/x")
    assert kept == GitUri("git+https://example.test/org/repo.git", "feature/x", None)
    assert not kept.pinned
    assert parse_git_uri("git+file:///tmp/repo").repository == "git+file:///tmp/repo"
    assert parse_git_uri("git+https://example.test/a#x/y").subdir == "x/y"
    with pytest.raises(ValueError, match="must start with 'git\\+'"):
        parse_git_uri("GIT+https://example.test/a")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("git+git@github.com:org/repo", "only git"),
        ("git+ssh://github.com/org/repo", "only git"),
        ("git+ftp://example.test/org/repo", "only git"),
        ("git+https://user:secret@example.test/org/repo", "userinfo"),
        ("git+https://example.test/org/repo?x=1", "query"),
        ("git+https://example.test/org/repo@", "empty ref"),
        ("git+https://example.test/org/repo@--upload-pack=x", "must not start with '-'"),
        ("git+https://example.test/org/repo#", "empty subdirectory"),
        ("git+https://example.test/org/repo#/abs", "plain relative"),
        ("git+https://example.test/org/repo#a\\b", "plain relative"),
        ("git+https://example.test/org/repo#a//b", "plain relative"),
        ("git+https://example.test/org/repo#./a", "plain relative"),
        ("git+https://example.test/org/repo#a/../b", "plain relative"),
        ("git+https:///org/repo", "must name a host"),
        ("git+https://example.test", "repository path"),
        ("git+https://example.test/org repo", "whitespace"),
        ("git+https://example.test/org\x07repo", "control"),
    ],
)
def test_parse_rejects(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_git_uri(text)


def test_every_ref_form_yields_the_full_hash(tmp_path: Path) -> None:
    root, first = _repository(tmp_path / "repo", {"sub": "thing"})
    _git(root, "tag", "v1")
    second = _commit(root, "two")
    base = f"git+file://{root}"
    expected = {"": second, "@main": second, "@v1": first, f"@{first[:8]}": first, f"@{first.upper()}": first}
    for ref, commit in expected.items():
        canonical, tree = fetch_git_checkout(f"{base}{ref}#sub")
        assert str(canonical) == f"{base}@{commit}#sub"
        assert (tree / "sub" / _MARKER).is_file() and not (tree / ".git").exists()
        assert tree == data_home() / "git" / tree.parent.name / commit
    checkout = json.loads(next((data_home() / "git").glob("*/*.json")).read_text(encoding="utf-8"))
    assert checkout["format"] == "httk-git-checkout" and checkout["repository"] == base


def test_pinned_cache_hit_runs_no_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, commit = _repository(tmp_path / "repo", {"": "thing"})
    uri = f"git+file://{root}@{commit}"
    member = _install(uri)
    shutil.rmtree(root)
    monkeypatch.setattr(git_sources, "_git", _refuse)
    entry = next((data_home() / "things" / "installed").glob("*.json"))
    time.sleep(0.001)
    again = _install(uri)
    assert again.uri == uri and again.referenced_at > member.referenced_at
    document = json.loads(entry.read_text(encoding="utf-8"))
    assert document == {
        "format": "httk-git-installed",
        "format_version": 1,
        "kind": "things",
        "uri": uri,
        "repository": f"git+file://{root}",
        "commit": commit,
        "subdir": None,
        "names": ["thing"],
        "referenced_at": again.referenced_at,
    }
    assert cached_git_checkout(uri) == again.path


def test_missing_marker_errors_hint_at_the_subdirectory(tmp_path: Path) -> None:
    root, commit = _repository(tmp_path / "multi", {"a": "a", "b": "b"})
    with pytest.raises(ValueError, match=r"no top-level marker.toml.*#subdir.*a, b"):
        _install(f"git+file://{root}")
    with pytest.raises(ValueError, match=rf"'c' is not a directory in git\+file://{root} at {commit}"):
        _install(f"git+file://{root}#c")
    (root / "empty").mkdir()
    (root / "empty" / "README").write_text("x", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "empty")
    with pytest.raises(ValueError, match="'empty' has no marker.toml"):
        _install(f"git+file://{root}#empty")
    assert installed_git_members("things") == ()


def test_rejected_member_is_not_installed(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path / "repo", {"": "thing"})

    def invalid(member: Path) -> tuple[str, ...]:
        raise ValueError("bad member")

    with pytest.raises(ValueError, match="bad member"):
        install_git_member("things", f"git+file://{root}", _MARKER, invalid)
    assert not (data_home() / "things").exists()


def test_latest_reference_wins_within_a_lineage(tmp_path: Path) -> None:
    root, first = _repository(tmp_path / "repo", {"sub": "thing"})
    second = _commit(root, "two")
    base = f"git+file://{root}"
    _install(f"{base}@{first}#sub")
    _install(f"{base}@{second}#sub")
    chosen = resolve_installed_name("things", "thing")
    assert chosen is not None and chosen.commit == second
    _install(f"{base}@{first}#sub")
    chosen = resolve_installed_name("things", "thing")
    assert chosen is not None and chosen.commit == first and chosen.path == cached_git_checkout(chosen.uri) / "sub"
    assert resolve_installed_name("things", "other") is None
    assert [member.commit for member in installed_git_members("things")] == sorted([first, second])


def test_two_lineages_claiming_one_name_conflict(tmp_path: Path) -> None:
    one, _ = _repository(tmp_path / "one", {"": "thing"})
    two, _ = _repository(tmp_path / "two", {"": "thing"})
    _install(f"git+file://{one}")
    _install(f"git+file://{two}")
    with pytest.raises(ValueError, match="several installed git things.*by its URI"):
        resolve_installed_name("things", "thing")


def test_cache_only_lookups_never_run_git_or_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, commit = _repository(tmp_path / "repo", {"": "thing"})
    monkeypatch.setattr(git_sources, "_git", _refuse)
    for uri in (f"git+file://{root}", f"git+file://{root}@main", f"git+file://{root}@{commit}"):
        assert cached_git_checkout(uri) is None
        assert installed_git_member("things", uri) is None
    assert installed_git_members("things") == ()
    assert resolve_installed_name("things", "thing") is None
    with pytest.raises(ValueError, match="no installed"):
        uninstall_git_members("things", f"git+file://{root}")
    assert not data_home().exists()


def test_malformed_entries_are_skipped(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    root, commit = _repository(tmp_path / "repo", {"": "thing"})
    member = _install(f"git+file://{root}")
    installed = data_home() / "things" / "installed"
    (installed / "bogus.json").write_text("{}", encoding="utf-8")
    entry = next(path for path in installed.glob("*.json") if path.name != "bogus.json")
    moved = installed / ("0" * 32 + ".json")
    moved.write_text(entry.read_text(encoding="utf-8"), encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="httk.core.git_sources"):
        assert [found.uri for found in installed_git_members("things")] == [member.uri]
    assert caplog.text.count("Skipping installed git things entry") == 2
    shutil.rmtree(cached_git_checkout(member.uri) or tmp_path / "missing")
    moved.unlink()
    (installed / "bogus.json").unlink()
    assert installed_git_members("things") == ()
    assert installed_git_member("things", f"git+file://{root}@{commit}") is None


def test_uninstall_selectors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, first = _repository(tmp_path / "repo", {"a": "alpha", "b": "beta"})
    second = _commit(root, "two")
    base = f"git+file://{root}"
    for uri in (f"{base}@{first}#a", f"{base}@{second}#a", f"{base}@{first}#b", f"{base}@{second}#b"):
        _install(uri)
    monkeypatch.setattr(git_sources, "_git", _refuse)
    removed = uninstall_git_members("things", f"{base}@{first.upper()}#a")
    assert [member.uri for member in removed] == [f"{base}@{first}#a"]
    assert installed_git_member("things", f"{base}@{first}#a") is None
    assert installed_git_member("things", f"{base}@{second}#a") is not None
    assert [member.uri for member in uninstall_git_members("things", f"{base}@main#b")] == sorted(
        [f"{base}@{first}#b", f"{base}@{second}#b"]
    )
    assert [member.uri for member in uninstall_git_members("things", "alpha")] == [f"{base}@{second}#a"]
    assert installed_git_members("things") == ()
    assert cached_git_checkout(f"{base}@{first}") is not None  # the checkout cache stays
    for selector in ("alpha", f"{base}#a"):
        with pytest.raises(ValueError, match="no installed git things match"):
            uninstall_git_members("things", selector)


def test_kind_must_be_a_plain_name() -> None:
    for kind in ("", "../x", "Templates", "a/b", "git"):
        with pytest.raises(ValueError, match="kind"):
            installed_git_members(kind)
