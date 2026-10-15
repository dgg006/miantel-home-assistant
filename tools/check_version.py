"""Comprobar que la etiqueta, el manifiesto y el componente coinciden."""

import ast
import json
import sys

from audit_public import ROOT


def check_version(tag, root=ROOT):
    component = root / "custom_components/miantel"
    manifest = json.loads((component / "manifest.json").read_text(encoding="utf-8"))
    tree = ast.parse((component / "const.py").read_text(encoding="utf-8"))
    version = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets)
    )
    if tag != "v" + manifest["version"] or version != manifest["version"]:
        raise ValueError("La etiqueta y las versiones de la integración no coinciden")
    return version


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python tools/check_version.py vVERSION")
    print("Versión comprobada:", check_version(sys.argv[1]))
