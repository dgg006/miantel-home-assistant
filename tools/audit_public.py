"""Check public text without printing matched sensitive values."""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP_FILES = {
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "hacs.json",
    "pyproject.toml",
    "requirements-dev.txt",
    ".gitignore",
    ".gitattributes",
}
FOLDERS = {"custom_components", "tests", "tools", "docs", ".github"}
SKIP = {"__pycache__", ".pytest_cache", ".ruff_cache", ".git", "dist", ".venv"}
EXTENSIONS = {".py", ".json", ".html", ".md", ".yml", ".yaml", ".toml", ".txt"}
BRAND_IMAGES = {"custom_components/miantel/brand/icon.png"}
TEXT_ASSETS = {"docs/agregar-a-hacs.svg"}


def public_files(root=ROOT):
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in SKIP for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError("Symlinks are not allowed")
        if not path.is_file():
            continue
        if len(relative.parts) == 1 and path.name in TOP_FILES:
            yield path
        elif relative.as_posix() in BRAND_IMAGES:
            if not path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("Invalid brand image")
            yield path
        elif relative.as_posix() in TEXT_ASSETS:
            yield path
        elif relative.parts[0] in FOLDERS and path.suffix in EXTENSIONS:
            yield path
        else:
            raise ValueError(f"Unexpected public file: {relative.as_posix()}")


def findings(text, forbidden=()):
    rules = []
    if re.search(r"[A-Za-z]:[\\/]Users[\\/]", text):
        rules.append("personal filesystem path")
    if re.search(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", text):
        rules.append("JWT-shaped value")
    if any(value and value in text for value in forbidden):
        rules.append("private reference value")
    return rules


def audit(root=ROOT, forbidden=(), release=False):
    failures = []
    for path in public_files(root):
        content = path.read_bytes().decode("latin-1" if path.suffix == ".png" else "utf-8")
        for rule in findings(content, forbidden):
            failures.append(f"{path.relative_to(root).as_posix()}: {rule}")
    manifest = json.loads((root / "custom_components/miantel/manifest.json").read_text())
    if release:
        from set_repository import hacs_url, repository_url

        metadata = json.loads((root / "docs/repository.json").read_text(encoding="utf-8"))
        full_name = metadata.get("full_name")
        try:
            if not isinstance(full_name, str):
                raise ValueError("Repository not set")
            url = repository_url("https://github.com/" + full_name)
        except (ValueError, TypeError, argparse.ArgumentTypeError):
            failures.append("repository.json: public repository URL is pending")
            return failures
        if manifest.get("documentation") != url or manifest.get("issue_tracker") != url + "/issues":
            failures.append("manifest.json: repository references do not match")
        if not manifest.get("codeowners"):
            failures.append("manifest.json: code owner is missing")
        if not metadata.get("description") or "Antel Uruguay" not in metadata["description"]:
            failures.append("repository.json: Spanish description for Antel Uruguay is missing")
        if not metadata.get("topics") or metadata.get("has_issues") is not True:
            failures.append("repository.json: topics or issue settings are missing")
        hacs = json.loads((root / "hacs.json").read_text(encoding="utf-8"))
        if hacs.get("country") != "UY" or hacs.get("homeassistant") != "2026.10.0":
            failures.append("hacs.json: country or minimum version does not match")
        domains = {
            p.name
            for p in (root / "custom_components").iterdir()
            if p.is_dir() and p.name not in SKIP
        }
        if domains != {"miantel"}:
            failures.append("custom_components: expected exactly one integration")
        readme = (root / "README.md").read_text(encoding="utf-8")
        if hacs_url(full_name) not in readme or "docs/agregar-a-hacs.svg" not in readme:
            failures.append("README.md: HACS button does not match repository")
        if not (root / "docs/agregar-a-hacs.svg").is_file():
            failures.append("README.md: HACS button image is missing")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", action="store_true")
    parser.add_argument(
        "--forbidden-file",
        type=Path,
        help="External private JSON list of strings; never copied or printed",
    )
    args = parser.parse_args()
    forbidden = []
    if args.forbidden_file:
        if args.forbidden_file.resolve().is_relative_to(ROOT):
            parser.error("Private reference file must be outside the public project")
        forbidden = json.loads(args.forbidden_file.read_text(encoding="utf-8-sig"))
        if not isinstance(forbidden, list) or not all(isinstance(v, str) for v in forbidden):
            parser.error("Expected a JSON list of strings")
    try:
        failures = audit(forbidden=forbidden, release=args.release)
    except (ValueError, UnicodeError):
        raise SystemExit("Audit failed: unexpected file or encoding") from None
    if failures:
        print("\n".join(failures))
        raise SystemExit(1)
    print("Public source audit passed")


if __name__ == "__main__":
    main()
