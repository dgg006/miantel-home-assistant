"""Build local ZIPs from the audited public allowlist; never publish."""

import json
from zipfile import ZIP_DEFLATED, ZipFile

from audit_public import ROOT, audit, public_files


def build(root=ROOT):
    failures = audit(root)
    if failures:
        raise ValueError("Public audit must pass before packaging")
    version = json.loads((root / "custom_components/miantel/manifest.json").read_text())["version"]
    files = list(public_files(root))
    target = root / "dist"
    target.mkdir(exist_ok=True)
    paths = []
    for suffix, component_only in (("install", True), ("source", False)):
        archive = target / f"miantel-{version}-{suffix}.zip"
        with ZipFile(archive, "w", compression=ZIP_DEFLATED) as output:
            for path in files:
                relative = path.relative_to(root)
                if component_only and relative.parts[0] != "custom_components":
                    continue
                output.write(path, relative.as_posix())
        # Inspect the stored bytes, not just the original source tree.
        with ZipFile(archive) as output:
            if output.testzip() is not None:
                raise ValueError("Archive integrity check failed")
            expected = {
                p.relative_to(root).as_posix()
                for p in files
                if not component_only or p.relative_to(root).parts[0] == "custom_components"
            }
            if set(output.namelist()) != expected:
                raise ValueError("Archive allowlist mismatch")
        paths.append(archive)
    return paths


if __name__ == "__main__":
    for path in build():
        print(path.name)
