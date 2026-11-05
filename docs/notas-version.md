# MiAntel para Home Assistant · Antel Uruguay

Versión estable 0.1.1 de MiAntel para Antel Uruguay. Estrena un ícono propio con mapa de Uruguay, servicios conectados y nodo amarillo, disponible en resolución normal y alta. Atiende la recomendación del revisor de HACS de reemplazar el recurso de la aplicación oficial. No cambia el funcionamiento, la configuración ni las entidades.

## Funciones incluidas

- Consulta de saldos, consumos de datos y facturación según la información disponible en MiAntel.
- Selección de servicios y frecuencia de actualización desde las opciones.
- Agrupación reversible de fibra y teléfono fijo en un mismo dispositivo.
- Modalidad de factura compartida mediante elección del servicio de consulta, sin sumar importes duplicados.
- Ícono propio de la integración comunitaria, compatibilidad con español latinoamericano y diagnósticos sin datos de cuenta.

## Instalación

Buscar **MiAntel** directamente en HACS: la integración ya fue incorporada al catálogo. El botón de repositorio personalizado sigue disponible como alternativa en la documentación. Descargar la integración y reiniciar Home Assistant. Luego agregar MiAntel desde Dispositivos y servicios e ingresar las credenciales de TuID en la propia instalación. Si ya estaba configurada, actualizar y reiniciar; se conservan la configuración y las entidades.

Requiere Home Assistant 2026.10 o posterior. También se incluye un archivo ZIP para instalación manual.

## Validación y límites

Se verificaron instalación, lecturas y pantallas de configuración en Home Assistant 2026.10.1. Se informó aproximadamente tres semanas de uso sin problemas en una instalación y se ejecutaron 85 pruebas automáticas con datos ficticios. Las pruebas con más cuentas siguen pendientes. Si TuID solicita un código adicional, esta versión no permite completarlo. Los cambios de formato de MiAntel pueden requerir ajustes.

Proyecto independiente, sin afiliación con Antel. No realiza pagos, recargas ni modificaciones de servicios.
