"""Per-user operator identity: keys, named identities, resolution, signing."""

from pathlib import Path

import pytest

from httk.core.identity import (
    add_identity,
    ensure_identity_key,
    identity_key_paths,
    identity_public_key,
    identity_seed,
    import_v1_identity,
    initialize_identity,
    local_public_keys,
    read_identity_config,
    remove_identity,
    resolve_operator_identity,
    set_default_identity,
    sign_document,
    verify_document,
    write_identity_config,
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTK_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("HTTK_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)


def test_add_identity_creates_key_with_permissions_and_default() -> None:
    values = add_identity("alice", "Alice", "alice@example.test")
    assert values["default_identity"] == "alice"
    assert identity_key_paths("alice")[0].stat().st_mode & 0o777 == 0o600
    assert identity_key_paths("alice")[1].exists()


def test_add_second_identity_keeps_default_unless_requested() -> None:
    add_identity("alice", "Alice", "alice@example.test")
    values = add_identity("bob", "Bob", "bob@example.test")
    assert values["default_identity"] == "alice"
    values = add_identity("ci_bot", "CI", "ci@example.test", make_default=True)
    assert values["default_identity"] == "ci_bot"


def test_add_succeeds_without_default_in_existing_multi_identity_config() -> None:
    write_identity_config(
        {
            "identities": {
                "alice": {"name": "Alice", "email": "alice@example.test"},
                "bob": {"name": "Bob", "email": "bob@example.test"},
            },
        }
    )
    values = add_identity("carol", "Carol", "carol@example.test")
    configured = values["identities"]
    assert isinstance(configured, dict)
    assert set(configured) == {"alice", "bob", "carol"}
    assert "default_identity" not in values


def test_resolution_order_and_literal_selector() -> None:
    assert identity_seed() is None
    with pytest.raises(ValueError, match="unknown identity"):
        resolve_operator_identity("missing")

    add_identity("alice", "Alice", "alice@example.test")
    add_identity("bob", "Bob", "bob@example.test")
    assert resolve_operator_identity("alice").label == "Alice <alice@example.test>"
    # The first-added identity is the default.
    assert resolve_operator_identity(None).short == "alice"
    literal = resolve_operator_identity("<forward@example.test>")
    assert literal.label == " <forward@example.test>"
    assert literal.seed_path == resolve_operator_identity("alice").seed_path
    literal_signed = sign_document({"format": "literal"}, seed_path=literal.seed_path)
    assert verify_document(literal_signed).valid
    with pytest.raises(ValueError, match="alice, bob"):
        resolve_operator_identity("missing")


@pytest.mark.parametrize(
    ("email", "expected"),
    (("Alice.Bob@example.test", "alice-bob"), ("___@example.test", "operator")),
)
def test_initialize_identity_derives_short_and_creates_named_default(email: str, expected: str) -> None:
    created, identity = initialize_identity("User", email)
    assert created
    assert identity.short == expected
    assert identity.seed_path == identity_key_paths(expected)[0]
    assert identity_key_paths(expected)[0].exists()
    values = read_identity_config()
    assert "name" not in values and "email" not in values
    assert values["default_identity"] == expected


def test_initialize_identity_is_idempotent() -> None:
    created, first = initialize_identity("First", "first@example.test")
    seed_before = first.seed_path.read_bytes()  # type: ignore[union-attr]
    config_before = read_identity_config()
    assert created

    created, second = initialize_identity("Second", "second@example.test")
    assert not created and second == first
    assert read_identity_config() == config_before
    assert first.seed_path.read_bytes() == seed_before  # type: ignore[union-attr]


def test_literal_selector_without_config_is_unsigned() -> None:
    identity = resolve_operator_identity("Ext <e@x>")
    document = {"format": "test"}
    assert identity.seed_path is None
    assert sign_document(document, seed_path=identity.seed_path) == document


def test_literal_selector_does_not_hide_dangling_or_corrupt_config() -> None:
    write_identity_config(
        {
            "identities": {"alice": {"name": "Alice", "email": "alice@example.test"}},
            "default_identity": "missing",
        }
    )
    with pytest.raises(ValueError, match="default identity"):
        resolve_operator_identity("Ext <e@x>")

    write_identity_config({"identities": "corrupt"})
    with pytest.raises(ValueError, match="identities.*object"):
        resolve_operator_identity("Ext <e@x>")


@pytest.mark.parametrize(
    "selector",
    ("Alice <", "Alice <mail", "Alice <mail@x> trailing", "Alice <>", "Alice <mail>", "Alice<mail@x>"),
)
def test_malformed_literal_selector_is_rejected(selector: str) -> None:
    with pytest.raises(ValueError, match="NAME <EMAIL>"):
        resolve_operator_identity(selector)


def test_dangling_default_refuses_resolution_and_signing() -> None:
    write_identity_config(
        {
            "identities": {"alice": {"name": "Alice", "email": "alice@example.test"}},
            "default_identity": "missing",
        }
    )
    with pytest.raises(ValueError, match="default identity"):
        resolve_operator_identity(None)
    with pytest.raises(ValueError, match="default identity"):
        identity_seed()


def test_ambiguous_identities_refuse_signing() -> None:
    write_identity_config(
        {
            "identities": {
                "alice": {"name": "Alice", "email": "alice@example.test"},
                "bob": {"name": "Bob", "email": "bob@example.test"},
            },
        }
    )
    with pytest.raises(ValueError, match="identity default"):
        resolve_operator_identity(None)
    with pytest.raises(ValueError, match="identity default"):
        identity_seed()
    with pytest.raises(ValueError, match="identity default"):
        sign_document({"format": "test"})


def test_initialize_identity_rejects_ambiguous_identities_with_guidance() -> None:
    write_identity_config(
        {
            "identities": {
                "alice": {"name": "Alice", "email": "alice@example.test"},
                "bob": {"name": "Bob", "email": "bob@example.test"},
            },
        }
    )
    with pytest.raises(ValueError, match="httk identity default"):
        initialize_identity("New", "new@example.test")


def test_identity_key_paths_refuse_symlinks(tmp_path: Path) -> None:
    seed_path, public_path = identity_key_paths("alice")
    seed_path.parent.mkdir(parents=True)
    target = tmp_path / "target"
    target.write_text("not a key\n", encoding="ascii")

    seed_path.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        ensure_identity_key("alice")

    seed_path.unlink()
    public_path.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        ensure_identity_key("alice")
    public_path.unlink()

    ensure_identity_key("alice")
    seed_path.chmod(0o644)
    ensure_identity_key("alice")
    assert seed_path.stat().st_mode & 0o777 == 0o600


def test_symlinked_seed_is_refused_not_silently_unsigned(tmp_path: Path) -> None:
    real_seed, _ = ensure_identity_key("alice")
    link = tmp_path / "linked.seed"
    link.symlink_to(real_seed)
    with pytest.raises(ValueError):
        identity_seed(link)
    assert identity_seed(tmp_path / "absent.seed") is None


def test_seed_decode_error_on_malformed_seed() -> None:
    seed_path, _ = identity_key_paths("alice")
    seed_path.parent.mkdir(parents=True)
    seed_path.write_text("not base64 !!!\n", encoding="ascii")
    with pytest.raises(ValueError, match="standard 32-byte Ed25519 seed"):
        identity_seed(seed_path)


def test_add_rejects_invalid_short_and_taken_short() -> None:
    with pytest.raises(ValueError, match="must match"):
        add_identity("Not-valid", "N", "n@example.test")
    add_identity("alice", "Alice", "alice@example.test")
    with pytest.raises(ValueError, match="already exists"):
        add_identity("alice", "Alice", "alice@example.test")


@pytest.mark.parametrize(
    ("name", "email"),
    (("Bad\nName", "bad@example.test"), ("Bad<Name", "bad@example.test"), ("Good", "bad"), ("Good", "bad > @x")),
)
def test_add_rejects_unforwardable_labels(name: str, email: str) -> None:
    with pytest.raises(ValueError, match="identity"):
        add_identity("bad", name, email)
    assert not identity_key_paths("bad")[0].exists()


def test_set_default_and_remove_keep_key_files() -> None:
    add_identity("alice", "Alice", "alice@example.test")
    add_identity("ci_bot", "CI", "ci@example.test", make_default=True)
    assert set_default_identity("alice")["default_identity"] == "alice"
    with pytest.raises(ValueError, match="unknown identity"):
        set_default_identity("nope")

    seed_path = identity_key_paths("ci_bot")[0]
    values = remove_identity("ci_bot")
    assert seed_path.exists()
    assert set(values["identities"]) == {"alice"}  # type: ignore[arg-type]
    assert read_identity_config()["default_identity"] == "alice"


def test_named_signing_round_trip_and_public_key() -> None:
    add_identity("alice", "Alice", "alice@example.test")
    default_signed = sign_document({"format": "test"})
    expected = "ed25519:" + identity_key_paths("alice")[1].read_text(encoding="ascii").strip()
    assert default_signed["operator_key"] == expected
    assert identity_public_key(resolve_operator_identity("alice").seed_path) == expected

    signed = sign_document({"format": "test"}, seed_path=resolve_operator_identity("alice").seed_path)
    assert verify_document(signed).valid
    assert signed["operator_key"] == expected


def test_local_public_keys_lists_configured_identity_keys() -> None:
    add_identity("alice", "Alice", "alice@example.test")
    add_identity("bob", "Bob", "bob@example.test")
    _, bob_public = identity_key_paths("bob")
    expected = [
        identity_public_key(identity_key_paths("alice")[0]),
        identity_public_key(identity_key_paths("bob")[0]),
    ]
    bob_public.unlink()
    assert local_public_keys() == expected


def test_local_public_keys_uses_seed_when_public_file_is_tampered() -> None:
    add_identity("alice", "Alice", "alice@example.test")
    add_identity("bob", "Bob", "bob@example.test")
    _, alice_public = identity_key_paths("alice")
    expected = local_public_keys()
    alice_public.write_bytes(identity_key_paths("bob")[1].read_bytes())
    assert local_public_keys() == expected


def test_local_public_keys_skips_an_identity_with_no_seed() -> None:
    add_identity("alice", "Alice", "alice@example.test")
    identity_key_paths("alice")[0].unlink()
    assert local_public_keys() == []


def test_local_public_keys_refuses_a_symlinked_seed(tmp_path: Path) -> None:
    add_identity("alice", "Alice", "alice@example.test")
    seed_path, _ = identity_key_paths("alice")
    target = tmp_path / "seed"
    target.write_bytes(seed_path.read_bytes())
    seed_path.unlink()
    seed_path.symlink_to(target)
    with pytest.raises(ValueError, match="identity seed"):
        local_public_keys()


def test_import_v1_identity_creates_named_identity(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    (legacy / "keys").mkdir(parents=True)
    (legacy / "config").write_text("[main]\nname = Imported\nemail = Mixed.Case@example.test\n", encoding="utf-8")
    result = import_v1_identity(legacy)
    assert result["short"] == "mixed-case"
    assert result["name"] == "Imported"
    assert read_identity_config()["default_identity"] == "mixed-case"


def test_import_v1_identity_is_idempotent(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "config").write_text("[main]\nname = Imported\nemail = imported@example.test\n", encoding="utf-8")
    first = import_v1_identity(legacy)
    values_before = read_identity_config()
    second = import_v1_identity(legacy)
    assert first == {"short": "imported", "name": "Imported", "email": "imported@example.test"}
    assert second == {}
    assert read_identity_config() == values_before


def test_import_v1_identity_does_not_record_legacy_label_when_configured(tmp_path: Path) -> None:
    add_identity("existing", "Existing", "existing@example.test")
    legacy = tmp_path / "legacy"
    (legacy / "keys").mkdir(parents=True)
    (legacy / "config").write_text("[main]\nname = Ignored\nemail = ignored@example.test\n", encoding="utf-8")
    (legacy / "keys" / "key1.pub").write_bytes(identity_key_paths("existing")[1].read_bytes())
    result = import_v1_identity(legacy)
    legacy_public_key = result["legacy_public_key"]
    assert isinstance(legacy_public_key, str)
    values = read_identity_config()
    assert values["identities"] == {"existing": {"name": "Existing", "email": "existing@example.test"}}
    assert "name" not in values and "email" not in values
    assert Path(legacy_public_key).is_file()


def test_absent_signature_is_accepted_and_tampering_is_rejected() -> None:
    add_identity("alice", "Alice", "alice@example.test")
    unsigned = {"format": "test", "value": 1}
    assert verify_document(unsigned).present is False
    assert verify_document(unsigned).valid is False

    signed = sign_document(unsigned)
    assert verify_document(signed).valid
    tampered = {**signed, "value": 2}
    result = verify_document(tampered)
    assert result.present and not result.valid


def test_identity_imports_first_in_fresh_subprocess() -> None:
    """Guard the identity<->project import cycle.

    ``httk.core.identity`` is a lower layer than ``httk.core.project`` and must
    import cleanly as the very first httk import in a fresh interpreter. Run it
    in a subprocess so a re-introduced cycle cannot hide behind an import order
    another test already warmed up.
    """

    import subprocess
    import sys

    subprocess.run([sys.executable, "-c", "import httk.core.identity"], check=True)
