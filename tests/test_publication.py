import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from audit_public import audit, findings, public_files
from build_release import build
from check_version import check_version
from set_repository import bind_repository, hacs_url, repository_url

ROOT = Path(__file__).resolve().parents[1]


def test_public_tree_is_clean():
    assert audit() == []
    manifest = json.loads((ROOT / "custom_components/miantel/manifest.json").read_text())
    if "example.invalid" in manifest["documentation"]:
        assert any("repository URL is pending" in item for item in audit(release=True))
    else:
        assert audit(release=True) == []


def test_sensitive_values_are_not_returned():
    marker = "FICTIONAL-PRIVATE-MARKER"
    result = findings(marker, [marker])
    assert result == ["private reference value"]
    assert marker not in str(result)


def test_translations_have_matching_structure():
    component = ROOT / "custom_components/miantel"
    en = json.loads((component / "translations/en.json").read_text(encoding="utf-8"))
    es = json.loads((component / "translations/es.json").read_text(encoding="utf-8"))

    def structure(value):
        return {k: structure(v) for k, v in value.items()} if isinstance(value, dict) else None

    assert structure(en) == structure(es)
    assert en == json.loads((component / "strings.json").read_text(encoding="utf-8"))
    assert (
        en == es == json.loads((component / "translations/es-419.json").read_text(encoding="utf-8"))
    )


def test_archives_contain_only_allowlisted_files(tmp_path):
    import shutil

    for path in public_files():
        dest = tmp_path / path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "secret.json").write_text("{}")
    with pytest.raises(ValueError):
        build(tmp_path)
    (tmp_path / "private" / "secret.json").unlink()
    for path in build(tmp_path):
        with ZipFile(path) as archive:
            assert all("private" not in name for name in archive.namelist())
            assert "custom_components/miantel/manifest.json" in archive.namelist()
            assert "custom_components/miantel/brand/icon.png" in archive.namelist()
            if "-source" in path.name:
                assert "docs/agregar-a-hacs.svg" in archive.namelist()


def test_repository_validation():
    assert repository_url("https://github.com/example/demo/") == "https://github.com/example/demo"
    with pytest.raises(Exception):
        repository_url("https://example.invalid/demo")


def test_all_python_sources_compile():
    for path in public_files():
        if path.suffix == ".py":
            compile(path.read_text(encoding="utf-8"), path.name, "exec")


@pytest.fixture
def public_copy(tmp_path):
    import shutil

    for path in public_files():
        target = tmp_path / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    return tmp_path


def test_repository_binding_updates_button_owner_and_metadata(public_copy):
    from urllib.parse import parse_qs, urlsplit

    bind_repository("https://github.com/example/miantel-demo", public_copy)
    assert audit(public_copy, release=True) == []
    before = (public_copy / "README.md").read_bytes()
    bind_repository("https://github.com/example/miantel-demo", public_copy)
    assert (public_copy / "README.md").read_bytes() == before
    manifest = json.loads((public_copy / "custom_components/miantel/manifest.json").read_text())
    assert manifest["codeowners"] == ["@example"]
    assert list(manifest) == ["domain", "name"] + sorted(key for key in manifest if key not in {'domain', 'name'})
    assert manifest["issue_tracker"] == "https://github.com/example/miantel-demo/issues"
    query = parse_qs(urlsplit(hacs_url("example/miantel-demo")).query)
    assert query == {
        "owner": ["example"],
        "repository": ["miantel-demo"],
        "category": ["integration"],
    }


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/example/demo",
        "https://example.invalid/demo",
        "https://github.com/example/demo?token=ficticio",
        "https://github.com/example/demo#fragment",
        "https://example@github.com/example/demo",
        "https://github.com/example/..",
    ],
)
def test_invalid_repository_urls_are_rejected(url):
    with pytest.raises(Exception):
        repository_url(url)


def test_release_audit_detects_missing_button_and_mismatched_metadata(public_copy):
    (public_copy / "docs/agregar-a-hacs.svg").unlink()
    assert any("button image is missing" in item for item in audit(public_copy, release=True))


def test_release_tag_and_component_versions_agree(public_copy):
    manifest = json.loads((public_copy / "custom_components/miantel/manifest.json").read_text())
    assert check_version("v" + manifest["version"], public_copy) == manifest["version"]
    with pytest.raises(ValueError):
        check_version("v0.0.0", public_copy)
    (public_copy / "custom_components/miantel/const.py").write_text('VERSION = "0.0.0"\n')
    with pytest.raises(ValueError):
        check_version("v" + manifest["version"], public_copy)
