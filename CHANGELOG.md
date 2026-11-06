# Cambios

## 0.2.0 — 2026-11-06

### Nuevas consultas de solo lectura

- Destinos gratis para llamadas a celulares, SMS y teléfonos fijos, y números amigos con tarifa preferencial. Cantidad configurada y atributos con números, capacidad y lugares libres.
- Recargas de saldo vigentes, con el saldo y vencimiento individual en los atributos.
- Desglose del gasto de recargas en llamadas, datos, SMS y otros, junto con minutos hablados, datos usados y SMS enviados.
- Inicio y fin del ciclo de consumo, renovación del cupo y días restantes cuando la web permite verificarlos.
- Velocidades contratadas de bajada y subida de fibra, diferenciando el plan actual de las ofertas.
- Indicador de roaming habilitado o deshabilitado, sin controles para cambiarlo.

### Correcciones y comportamiento

- Vencimiento del saldo en prepagos que requieren consultar el detalle del consumo; si hay varias recargas se muestra el vencimiento más próximo.
- Navegación JSF con el estado actualizado, incluso cuando la respuesta parcial no incluye el campo oculto en los formularios.
- Preparación de certificados de la conexión segura en el trabajo de consulta en segundo plano, evitando bloquear el arranque de Home Assistant.
- Las consultas nuevas se limitan a los servicios seleccionados. Las velocidades contratadas se conservan en memoria hasta 24 horas.
- Los fallos de una sección no se convierten en cantidades cero ni reemplazan lecturas válidas de otras secciones. Los límites de solicitudes y los errores de autenticación mantienen su tratamiento específico.
- Se conservan cuenta, opciones e identificadores de las entidades existentes. Toda la interfaz y las notas de versión están en español.

### Validación

149 pruebas automáticas con datos ficticios. Lecturas contrastadas con la web en Home Assistant 2026.11. Las modalidades sin información disponible no se presentan como verificadas. No se agregan reclamos, edición de destinos, cambios de roaming ni otras operaciones sobre los servicios.

## 0.1.1 — 2026-11-05

Nuevo ícono propio con mapa de Uruguay y servicios conectados, en tamaños normal y de alta resolución. Reemplaza el ícono extraído de la aplicación Android. Documentación actualizada para instalar buscando MiAntel en el catálogo de HACS, donde ya fue aprobada. Sin cambios en las consultas, configuración ni entidades.

## 0.1.0 — 2026-11-05

Primera versión estable, con el mismo funcionamiento de 0.1.0-beta.4. Publicada tras aproximadamente tres semanas de uso sin problemas reportados en una instalación. Documentación actualizada y 85 pruebas automáticas con datos ficticios. La versión se publica sin la marca de prelanzamiento para permitir su instalación normal desde HACS.

## 0.1.0-beta.4

Nombres y modelos en español; variante es-419 y respaldo en español. Edición del nombre y la modalidad de facturación de agrupaciones existentes. Factura compartida mediante selección expresa del servicio de consulta, sin sumar importes ni reemplazar consultas fallidas. Presentación duplicada oculta de forma reversible, conservando entidades e historial. Distinción entre cantidad de facturas e indicador de facturas pendientes.

## 0.1.0-beta.3

Agrupación manual y reversible de fibra y teléfono fijo desde las opciones. Cada par se muestra como un dispositivo y conserva sus entidades e importes independientes. No hay suma de deuda ni inferencia automática de facturas compartidas. Identificadores de entidades estables al agrupar y desagrupar. Pendiente de prueba completa en Home Assistant.

## 0.1.0-beta.2

Selector y dispositivos con el alias visible de MiAntel, sin código JavaScript ni identificadores repetidos. Ícono original de la aplicación incluido mediante la carpeta local de marca de Home Assistant. Preparada para aplicar después de la prueba inicial.

## 0.1.0-beta.1

Primera preparación local: cliente web TuID, selección de servicios, sensores de saldo, datos y facturación, reautenticación, traducciones español/inglés y diagnósticos mínimos. Pruebas independientes con datos ficticios. Instalación real en Home Assistant pendiente.
