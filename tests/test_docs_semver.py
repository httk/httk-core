import pytest

from httk.core.docs.semver import Version, VersionError, highest_version, is_release_dir_name, parse_tag, parse_version


def test_versions_parse_and_sort() -> None:
    assert str(parse_version("2.10.0")) == "2.10.0"
    assert parse_version("2.1.0").tag == "v2.1.0"
    assert sorted([Version(2, 0, 0), Version(1, 9, 9)]) == [Version(1, 9, 9), Version(2, 0, 0)]
    assert highest_version(iter([Version(1, 0, 0), Version(2, 0, 0)])) == Version(2, 0, 0)
    assert highest_version([]) is None


@pytest.mark.parametrize("text", ["01.2.3", "1.02.3", "1.2.03", "1.2", "1.2.3-alpha", "v1.2.3", "garbage"])
def test_invalid_versions(text: str) -> None:
    with pytest.raises(VersionError):
        parse_version(text)


def test_tags_and_directory_names() -> None:
    assert parse_tag("v0.0.0") == Version(0, 0, 0)
    assert is_release_dir_name("v2.1.0")
    assert not is_release_dir_name("v2.1.0-dev")
