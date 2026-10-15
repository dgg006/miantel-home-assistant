# MiAntel para Home Assistant · Antel Uruguay

Primera versión pública de prueba de la integración comunitaria de MiAntel para los servicios de Antel Uruguay. Interfaz y documentación en español.

## Funciones incluidas

- Consulta de saldos, consumos de datos y facturación según la información disponible en MiAntel.
- Selección de servicios y frecuencia de actualización desde las opciones.
- Agrupación reversible de fibra y teléfono fijo en un mismo dispositivo.
- Modalidad de factura compartida mediante elección del servicio de consulta, sin sumar importes duplicados.
- Ícono original de MiAntel, compatibilidad con español latinoamericano y diagnósticos sin datos de cuenta.

## Instalación

Agregar el repositorio personalizado desde el botón de HACS incluido en la documentación, descargar la integración y reiniciar Home Assistant. Luego agregar MiAntel desde Dispositivos y servicios e ingresar las credenciales de TuID en la propia instalación.

Requiere Home Assistant 2026.10 o posterior. También se incluye un archivo ZIP para instalación manual.

## Estado de prueba

Se verificaron instalación, lecturas y pantallas de configuración en Home Assistant 2026.10.1. Las pruebas con más cuentas y durante períodos prolongados siguen pendientes. Si TuID solicita un código adicional, esta versión no permite completarlo. Los cambios de formato de MiAntel pueden requerir ajustes.

Proyecto independiente, sin afiliación con Antel. No realiza pagos, recargas ni modificaciones de servicios.
