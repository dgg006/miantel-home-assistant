# MiAntel para Home Assistant · Antel Uruguay

<img src="custom_components/miantel/brand/icon.png" alt="Ícono de MiAntel" width="96" height="96">

Integración comunitaria para consultar en **Home Assistant los servicios de Antel Uruguay** mediante MiAntel: saldos de líneas móviles, consumo de internet e información de facturación, según los datos disponibles en cada servicio. Toda la interfaz está en español, incluido español latinoamericano.

**Versión estable 0.2.0.** Es un proyecto independiente, sin afiliación con Antel. Solo consulta información: no realiza pagos, recargas ni cambios de servicios.

<!-- HACS:BEGIN -->
[![Agregar repositorio a HACS](docs/agregar-a-hacs.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=dgg006&repository=miantel-home-assistant&category=integration)
<!-- HACS:END -->

## Qué podés consultar

| Información | Qué muestra |
| --- | --- |
| Saldo móvil | Saldo disponible y vencimiento, cuando MiAntel los informa. |
| Datos de internet | Consumo, datos incluidos y nombre del plan. |
| Recargas de saldo | Cantidad vigente y detalle del saldo y vencimiento de cada recarga. |
| Consumo de recargas | Gasto en llamadas, datos, SMS y otros; minutos hablados, datos usados y SMS enviados, según la web. |
| Ciclo de consumo | Inicio, fin, próxima renovación del cupo y días restantes, cuando se pueden verificar. |
| Velocidad contratada | Bajada y subida de fibra correspondientes al plan actual. No es una prueba de velocidad. |
| Roaming | Indicador de habilitado o deshabilitado, sin control para modificarlo. |
| Destinos y amigos | Celulares y fijos para llamadas gratis, SMS gratis y números amigos con tarifa preferencial. |
| Facturación | Estado de facturación, cantidad e importe pendiente y próximo vencimiento, cuando el formato permite leerlos. |
| Avisos | Indicadores de facturas pendientes y vencidas. |
| Última factura | Importe y fecha de emisión; consulta opcional, desactivada inicialmente. |

La última factura emitida **no equivale a deuda pendiente**. Si una consulta falla, el dato afectado queda no disponible; el error no se convierte en saldo, deuda o consumo cero.

## Requisitos

- Cuenta de TuID con acceso a [MiAntel web](https://aplicaciones.antel.com.uy/miAntel/) y sus servicios asociados.
- Home Assistant **2026.10 o posterior**, con conexión a internet.
- Marketplace de Home Assistant o [HACS instalado](https://www.hacs.xyz/docs/use/) para usar la instalación recomendada.

No necesitás un emulador, el APK de MiAntel ni un token de Home Assistant para configurar esta integración.

## Instalar desde el Marketplace o HACS

Buscá **MiAntel** en el Marketplace de Home Assistant o en HACS. Abrí **MiAntel (Antel Uruguay)**, instalá la integración y reiniciá Home Assistant. Después seguí desde el paso 4 de abajo.

MiAntel fue incorporada al catálogo de HACS el 5 de noviembre de 2026. Si tu instancia todavía no la muestra, también podés usar el repositorio personalizado:

1. Presioná **Agregar repositorio a HACS**, arriba. Si My Home Assistant lo solicita, indicá la dirección de tu instalación de Home Assistant.
2. Confirmá el agregado del repositorio personalizado de tipo **Integración**.
3. Descargá **MiAntel (Antel Uruguay)** desde HACS y reiniciá Home Assistant.
4. Entrá a **Ajustes → Dispositivos y servicios → Añadir integración → MiAntel**.
5. Ingresá tus credenciales de TuID y elegí los servicios que querés consultar.

Después de descargar y reiniciar, también podés [abrir la configuración de MiAntel](https://my.home-assistant.io/redirect/config_flow_start/?domain=miantel).

El botón facilita el agregado como **repositorio personalizado**. La inclusión en el catálogo predeterminado de HACS es un trámite distinto.

### Si el botón no abre HACS

Abrí **HACS → menú de los tres puntos → Repositorios personalizados**, agregá la URL siguiente y elegí **Integración**:

<!-- REPOSITORY:BEGIN -->
[dgg006/miantel-home-assistant](https://github.com/dgg006/miantel-home-assistant)
<!-- REPOSITORY:END -->

Luego descargá la integración, reiniciá Home Assistant y seguí los pasos de configuración anteriores.

## Instalación manual

Copiá la carpeta `custom_components/miantel` de este repositorio dentro de `custom_components` en la configuración de Home Assistant. También podés extraer el archivo de instalación de una versión publicada: ya contiene esa estructura de carpetas. Reiniciá Home Assistant y agregá MiAntel desde Dispositivos y servicios.

Si ya usabas la instalación manual, mantené la misma cuenta configurada al pasar a HACS. El dominio de la integración sigue siendo `miantel`; no hace falta crear otra cuenta de integración.

## Servicios y actualización

Cada servicio aparece como un dispositivo, con las entidades correspondientes a los datos que MiAntel permite consultar. En **MiAntel → Configurar** podés cambiar los servicios seleccionados, la frecuencia de consulta y la lectura de la última factura.

La actualización es cada **60 minutos** de forma predeterminada; se puede ajustar entre 15 minutos y 24 horas. Consultar el histórico agrega solicitudes, por eso está desactivado inicialmente. Un servicio que desaparece de la cuenta queda no disponible.

### Recargas, destinos y consultas complementarias

**Recargas de saldo vigentes** muestra la cantidad. Al abrir los atributos de la entidad, `recargas` contiene el saldo y el vencimiento de cada una. **Vencimiento del saldo** muestra la fecha más próxima, incluyendo los prepagos que solo la muestran en el detalle del consumo de MiAntel.

Las cuatro categorías de **Destinos gratis** y **Números amigos** muestran la cantidad configurada. Sus atributos incluyen `numeros`, `capacidad` y `lugares_disponibles`. Son únicamente informativos: no se agregan, editan ni eliminan números desde la integración.

El desglose de gasto y consumo corresponde a las recargas de saldo del período mostrado por MiAntel; no representa necesariamente el consumo de regalos, bonos o paquetes independientes. No se crean lecturas ficticias para modalidades sin datos reconocidos. Los minutos consumidos no equivalen a minutos incluidos o restantes del plan.

Las fechas del ciclo y de renovación se contrastan con los días restantes que informa la web. Las velocidades son las contratadas, en Mbit/s, y se conservan en memoria hasta 24 horas para evitar consultar repetidamente el catálogo de planes. El estado de roaming indica su habilitación, no si el equipo está conectado en el extranjero.

Estas lecturas complementarias consultan únicamente los servicios seleccionados y pueden hacer que la primera actualización tarde más. Las entidades nuevas se crean según la información disponible; se pueden ocultar o deshabilitar desde Home Assistant. No hace falta volver a configurar una cuenta existente al actualizar.

## Agrupar fibra y teléfono fijo

1. Abrí las opciones de MiAntel y marcá **Agrupar fibra y teléfono**.
2. Elegí **Crear agrupación**, poné un nombre al dispositivo y seleccioná una fibra y un teléfono fijo.
3. Elegí la modalidad de facturación y terminá con **Guardar y terminar**.

Podés crear varios pares, cambiar sus nombres y deshacerlos después. Un servicio solo puede pertenecer a una agrupación. Los dos miembros deben estar seleccionados para que el par esté activo. Las lecturas se distinguen como **Fibra** y **Teléfono**, y los identificadores de las entidades se conservan junto con su historial.

### Factura compartida

Si teléfono y fibra se pagan en una misma factura, entrá a **Editar nombre o facturación** y elegí desde qué servicio permite consultarla MiAntel: desde la fibra o desde el teléfono.

Se mostrará una sola **Facturación**, sin sumar los importes de ambos servicios. La presentación repetida del otro servicio se oculta; sus entidades e historial se conservan. Si volvés a facturas separadas, se restaura la visibilidad que administraba la integración y se respetan las ocultaciones propias del usuario.

Esta asociación la elige el usuario. No se adivinan pares ni se consideran iguales dos facturas solo por tener el mismo importe. Si falla la consulta del servicio elegido, no se reemplaza con la del otro. Las agrupaciones existentes conservan su modalidad hasta que la cambies. No necesitás subir facturas a Home Assistant.

Las automatizaciones dirigidas al dispositivo pueden necesitar que elijas el dispositivo agrupado; los identificadores de las entidades se mantienen.

## Inicio de sesión y privacidad

La integración usa el acceso normal de MiAntel web mediante TuID. Las cookies permanecen en memoria y la sesión se vuelve a iniciar si vence. Las credenciales se guardan en la configuración local de Home Assistant para permitir ese ingreso.

Si se rechazan las credenciales, Home Assistant solicita volver a autenticarse. Ingresá la misma cuenta y su contraseña actual en el aviso de MiAntel; se conservan los servicios seleccionados y las opciones. Los errores de conexión se reintentan como problemas temporales, sin pedir otra contraseña. Un intento de recuperar la sesión no envía repetidamente la contraseña.

Si TuID pide SMS u otra verificación adicional, esta versión se detiene y requiere atención: todavía no permite completar ese paso. Que un ingreso no pida SMS no garantiza que nunca lo solicite.

El componente no registra credenciales, cookies ni páginas completas. Sus diagnósticos incluyen únicamente versión, opciones generales y estado de actualización; excluyen cuentas, números de servicios, alias e importes. No envía diagnósticos ni archivos a terceros. Los ejemplos y pruebas del repositorio utilizan datos ficticios.

## Actualizaciones y límites

HACS permite descargar las actualizaciones cuando estén disponibles. Después de actualizar, reiniciá Home Assistant. Las versiones experimentales se identifican como beta.

- Se comprobaron las lecturas complementarias en Home Assistant 2026.11, contrastándolas con MiAntel web y conservando las entidades y opciones anteriores. Las agrupaciones y factura compartida también se verificaron en Home Assistant 2026.10.1. La validación con más cuentas y modalidades de contrato sigue pendiente.
- Las páginas internas de MiAntel pueden cambiar sin aviso. Los formatos desconocidos se informan como desconocidos o no disponibles.
- Las facturas pendientes y vencidas tienen cobertura de pruebas con ejemplos ficticios; hace falta validar más formatos reales.
- En los formatos investigados, los tamaños que el sitio etiqueta como GB usan una convención binaria; las entidades usan GiB. Esta equivalencia debe revisarse ante servicios o formatos nuevos.
- No hay pagos, recargas, cambios de plan, altas ni bajas. Los formularios enviados se usan para iniciar sesión y consultar información.

## Ayuda y colaboración

Los reportes de errores y las propuestas de mejora se reciben en la sección **Incidencias** del repositorio. Describí el problema sin adjuntar credenciales, números de cuenta o servicios, facturas completas ni capturas sin anonimizar.

Para colaborar: [desarrollo y pruebas](docs/desarrollo.md), [protocolo y decisiones de diseño](docs/protocol.md) y [preparación de publicaciones](docs/publicacion.md).

El código y el nuevo ícono propio se distribuyen bajo licencia MIT. Las marcas MiAntel y Antel pertenecen a sus titulares; consultá la [información del ícono](docs/brand.md).
