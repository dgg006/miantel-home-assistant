# Protocolo y mantenimiento

El cliente sigue MiAntel web en `https://aplicaciones.antel.com.uy/miAntel/`. El proveedor de identidad es `https://eidas.tuid.uy/`. Solo admite HTTPS y esos dos servidores. No incorpora identificadores, contraseñas, tokens ni capturas de cuentas reales.

## Inicio de sesión

1. Abrir MiAntel y seguir su redirección a TuID.
2. Seleccionar «Usuario y contraseña» si aparece el selector.
3. Seguir los formularios de relevo con campos ocultos.
4. Enviar usuario y contraseña en sus respectivos formularios de TuID, una sola vez por intento.
5. Comprobar el retorno a MiAntel.

Los campos ocultos y los identificadores JSF se obtienen de la respuesta actual. No se reutiliza un ViewState fijo. Cualquier paso no reconocido, incluido un código adicional, detiene la autenticación. Un acceso no aceptado no genera un bucle de contraseñas.

## Consultas

La portada puede necesitar una llamada parcial JSF para completar `pnlAll`. Se reconoce únicamente el comando de carga correspondiente. Las respuestas XML parciales se leen sin entidades externas ni acceso a red. Se contemplan páginas con bytes Latin-1 pese a declarar UTF-8.

Los servicios se identifican mediante sus identificadores internos estables. Las tarjetas duplicadas para distintos tamaños de pantalla no generan entidades duplicadas. Se comprueba la cardinalidad informada cuando es positiva; el contador inicial cero puede permanecer sin actualizar después de cargar tarjetas mediante JSF.

Facturación usa `app/facturacion/facturas.jsf`. El histórico, opcional, se abre mediante el formulario y comando actuales de la página. Los importes usan Decimal; no se suman monedas distintas ni se interpreta un número desconocido como cero. Las fechas incompletas de vencimiento de saldo requieren concordancia con los días restantes para evitar inventar el año.

La renovación de sesión permite un nuevo inicio de sesión y una repetición de lectura. Las consultas se serializan en un hilo de trabajo de Home Assistant. Una limitación de solicitudes pospone la actualización; un fallo de facturación conserva los saldos y consumos válidos de esa lectura.

## Pruebas y tareas pendientes

Las agrupaciones se guardan como opciones locales explícitas: nombre, identificador de fibra, identificador de teléfono y modalidad de facturación. El identificador del grupo deriva del par, no de su nombre ni de la modalidad. El identificador original de cada entidad no cambia. Al recargar, se reasignan entidades existentes (también las deshabilitadas) a sus dispositivos correspondientes y solo se retiran dispositivos propios vacíos. Los identificadores de grupos no se incluyen en diagnósticos.

La modalidad compartida no fusiona información: presenta la facturación de un único servicio, elegido explícitamente, y marca como ocultas por la integración las entidades de facturación del otro. Las lecturas originales y sus identificadores se conservan. Se respetan ocultaciones del usuario y se restablece la visibilidad administrada por la integración al volver a separar. El fallo del origen elegido nunca activa una sustitución por el otro servicio. No se utiliza un importe ni una fecha de un PDF como prueba de deuda actual.

Los fixtures son completamente ficticios. Cubren navegación, errores de autenticación, expiración, decodificación, deuda desconocida, facturas, identificadores duplicados y destinos de red rechazados. No representan contratos o líneas de una persona.

Antes de una versión estable: validar instalación, opciones y reautenticación con Home Assistant 2026.10; observar sesiones durante varios días; ampliar formatos de facturas pendientes con muestras anonimizadas y autorización de sus titulares. Una prueba del cliente HTTP no equivale a una prueba del componente instalado.

Referencias de implementación: [config flows de Home Assistant](https://developers.home-assistant.io/docs/config_entries_config_flow_handler/) y [tratamiento de errores de configuración](https://developers.home-assistant.io/docs/integration_setup_failures/).
