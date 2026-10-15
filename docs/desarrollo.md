# Desarrollo y pruebas

La integración está en `custom_components/miantel`. El cliente web y las reglas de agrupación son independientes de Home Assistant y se prueban sin cuentas reales.

## Preparar el entorno

Usá un entorno virtual de Python. Para las pruebas del cliente se requiere Python 3.12 o posterior; Home Assistant 2026.10 requiere su propia versión compatible de Python, por eso la automatización usa Python 3.14.

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check .
python tools/audit_public.py --release
python tools/build_release.py
```

Las pruebas cubren extracción de servicios, navegación y autenticación simuladas, números y fechas, respuestas incompletas, errores de consulta, agrupación reversible, visibilidad de facturación y conservación de identificadores. Las pruebas del registro utilizan una simulación de su API; no sustituyen la comprobación dentro de Home Assistant.

## Archivos de instalación

`tools/build_release.py` genera dos archivos ZIP en `dist/`: uno con `custom_components/miantel` para instalación manual y otro con el proyecto publicable. Ambos usan una lista explícita de archivos admitidos. El material privado, las capturas, el APK y los entornos de desarrollo no pertenecen al proyecto publicable.

HACS descarga la integración desde la carpeta estándar del repositorio; no necesita leer esos ZIP ni usar `zip_release`.

## Colaborar

Usá datos ficticios en pruebas y ejemplos. No agregues credenciales, cookies, tokens, servicios reales ni facturas personales. La auditoría admite `--forbidden-file` con una lista JSON externa de valores privados para revisar posibles coincidencias sin mostrarlos. Ese archivo debe estar fuera del repositorio y no se incluye en los paquetes.

Los cambios se validan mediante pruebas, revisión de estilo y auditoría. Las acciones oficiales de HACS y hassfest se ejecutan en GitHub una vez publicado el repositorio; sus resultados se deben revisar antes de publicar una versión.
