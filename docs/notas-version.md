# MiAntel 0.2.0 · Antel Uruguay

Actualización estable con nuevas consultas de solo lectura para los servicios de Antel Uruguay. Disponible desde el catálogo del Marketplace de Home Assistant y HACS.

## Novedades

- **Destinos gratis y números amigos:** cantidad configurada por categoría; números, capacidad y lugares libres en los atributos de cada entidad. Incluye llamadas a celulares, SMS, llamadas a fijos y amigos con tarifa preferencial.
- **Recargas vigentes:** cantidad y detalle de saldo y vencimiento individual. Se corrige el vencimiento de los prepagos que lo muestran únicamente en el detalle del consumo; se toma la fecha más próxima.
- **Consumo de recargas:** gasto en llamadas, datos, SMS y otros, junto con minutos hablados, datos utilizados y SMS enviados cuando la web los informa.
- **Ciclo de consumo:** fechas de inicio y fin, próxima renovación del cupo y días restantes, con validación de las fechas.
- **Fibra:** velocidades contratadas de bajada y subida del plan actual, en Mbit/s. Son datos del contrato, no una medición de velocidad.
- **Roaming:** indicador de habilitado o deshabilitado, sin interruptor ni acciones para cambiarlo.

## Correcciones

Se actualiza el estado interno necesario para navegar entre las pantallas de MiAntel. La preparación de certificados de conexión se realiza en segundo plano para evitar bloquear el arranque de Home Assistant.

Si una consulta complementaria falla, no se inventan ceros ni se borran las otras lecturas válidas. Las consultas se limitan a los servicios seleccionados; las velocidades contratadas se conservan en memoria hasta 24 horas.

## Actualizar o instalar

Buscá **MiAntel (Antel Uruguay)** en el Marketplace de Home Assistant o HACS, descargá **0.2.0** y reiniciá Home Assistant. Se conservan la cuenta, las opciones y los identificadores de las entidades existentes. Las entidades nuevas aparecen según los datos disponibles en cada servicio y se pueden ocultar o deshabilitar.

Los números de destinos y el detalle de recargas se consultan abriendo los atributos de sus entidades. No se incluyen controles para modificar destinos, roaming, planes o servicios.

Requiere Home Assistant 2026.10 o posterior. También se incluyen archivos ZIP para instalación manual y código fuente.

## Validación y alcance

149 pruebas automáticas con datos ficticios y lecturas contrastadas con MiAntel web en Home Assistant 2026.11. Los minutos consumidos no equivalen a minutos incluidos o restantes; el desglose de recargas no representa necesariamente bonos o paquetes independientes. Las modalidades sin información reconocida no se presentan como verificadas. No se agregan reclamos.

Los diagnósticos excluyen credenciales, cookies, cuentas, números de servicios, destinos e importes. Los ejemplos públicos usan datos ficticios. Proyecto comunitario independiente, sin afiliación con Antel.
