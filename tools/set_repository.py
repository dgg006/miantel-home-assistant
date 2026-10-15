"""Set a chosen public repository URL without creating or publishing it."""

import argparse
import json
import re
from urllib.parse import urlencode

from audit_public import ROOT


def repository_url(value):
    if not re.fullmatch(r"https://github\.com/[A-Za-z0-9-]+/[A-Za-z0-9_.-]+/?", value):
        raise argparse.ArgumentTypeError("Expected an HTTPS GitHub repository URL")
    result = value.rstrip("/").removesuffix(".git")
    if result.rsplit("/", 1)[-1] in {"", ".", ".."}:
        raise argparse.ArgumentTypeError("Expected an HTTPS GitHub repository URL")
    return result


def hacs_url(full_name):
    owner, repository = full_name.split("/")
    return "https://my.home-assistant.io/redirect/hacs_repository/?" + urlencode(
        {"owner": owner, "repository": repository, "category": "integration"}
    )


def replace_block(content, name, replacement):
    pattern = rf"(<!-- {name}:BEGIN -->\n).*?(\n<!-- {name}:END -->)"
    result, count = re.subn(
        pattern, lambda match: match[1] + replacement + match[2], content, flags=re.DOTALL
    )
    if count != 1:
        raise ValueError("Missing or repeated repository documentation block")
    return result


def bind_repository(url, root=ROOT):
    url = repository_url(url)
    full_name = url.removeprefix("https://github.com/")
    owner, _ = full_name.split("/")
    manifest_path = root / "custom_components/miantel/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(documentation=url, issue_tracker=url + "/issues", codeowners=["@" + owner])
    manifest = {key: manifest[key] for key in ["domain", "name"] + sorted(
        key for key in manifest if key not in {"domain", "name"})}
    metadata_path = root / "docs/repository.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["full_name"] = full_name
    readme_path = root / "README.md"
    readme = replace_block(
        readme_path.read_text(encoding="utf-8"),
        "HACS",
        f"[![Agregar repositorio a HACS](docs/agregar-a-hacs.svg)]({hacs_url(full_name)})",
    )
    readme = replace_block(readme, "REPOSITORY", f"[{full_name}]({url})")
    for path, content in [
        (manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"),
        (metadata_path, json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"),
        (readme_path, readme),
    ]:
        path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", type=repository_url)
    args = parser.parse_args()
    bind_repository(args.url)
    print("Referencias y botón de HACS actualizados localmente; no se publicó nada")
