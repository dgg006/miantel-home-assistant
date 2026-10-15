# Publicación en GitHub y HACS

La configuración pública del repositorio está en `docs/repository.json`: nombre, descripción en español, temas y habilitación de incidencias. El botón de HACS y las referencias del manifiesto se mantienen juntos con `tools/set_repository.py`.

## Primera subida

El proyecto local preparado no crea repositorios remotos ni publica por sí mismo. Al decidir publicarlo:

1. Crear en la cuenta elegida el repositorio indicado en `docs/repository.json`, con visibilidad pública y sin archivos iniciales adicionales.
2. Aplicar su descripción en español, sus temas y habilitar las incidencias. HACS necesita esos datos de GitHub, además de los archivos del proyecto.
3. Subir la rama `main` del repositorio local preparado.
4. Esperar las pruebas y revisar los resultados de las validaciones oficiales de HACS y hassfest en Acciones de GitHub.
5. Probar el botón y la descarga desde HACS en una instalación de ensayo.

El repositorio funciona en HACS como repositorio personalizado. Aparecer en el catálogo predeterminado requiere una solicitud adicional y no se anuncia como aprobado de antemano.

## Comprobaciones antes de una versión

```sh
python -m pytest -q
python -m ruff check .
python tools/audit_public.py --release
python tools/check_version.py v0.1.0-beta.4
python tools/build_release.py
```

Para versiones futuras, actualizar de forma coherente `manifest.json`, `const.py`, el registro de cambios y las notas de versión. Los archivos de instalación están en `dist/`; esa carpeta no se sube como código al repositorio.

Al subir una etiqueta con prefijo `v`, la acción **Preparar versión** ejecuta las verificaciones y crea un **borrador de versión** con notas en español y los ZIP correspondientes. El borrador permite revisar el resultado antes de publicarlo. Subir una etiqueta no publica automáticamente ese borrador.

No se debe presentar la beta como estable: faltan pruebas prolongadas y con más cuentas. La publicación no debe incluir capturas reales, facturas, credenciales, tokens, cookies ni archivos privados de investigación.

## Cambiar la dirección del repositorio

Ejecutar `python tools/set_repository.py` seguido de la nueva URL HTTPS de GitHub. Se actualizan manifiesto, responsable, metadatos y botón de HACS. Revisar el responsable si el destino es una organización. Volver a ejecutar la auditoría antes de subir el cambio.

Referencias: [requisitos de integraciones para HACS](https://www.hacs.xyz/docs/publish/integration/), [descripción y configuración del repositorio](https://www.hacs.xyz/docs/publish/start/) y [acción oficial de validación](https://www.hacs.xyz/docs/publish/action/).
