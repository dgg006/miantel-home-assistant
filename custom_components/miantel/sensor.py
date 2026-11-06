"""Balance, data and invoice sensors."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass

from .entity import MiAntelEntity
from .web.models import BillingStatus

DESTINATION_KEYS = ("free_call_mobile", "free_sms", "free_call_fixed", "friend_numbers")

METRIC_DESCRIPTIONS = {
    "cycle_start": ("Inicio del ciclo", SensorDeviceClass.DATE, None, "mdi:calendar-start"),
    "cycle_end": ("Fin del ciclo", SensorDeviceClass.DATE, None, "mdi:calendar-end"),
    "renewal_date": ("Renovación del cupo", SensorDeviceClass.DATE, None, "mdi:calendar-refresh"),
    "renewal_days": ("Días para renovar el cupo", SensorDeviceClass.DURATION, "d", "mdi:timer-sand"),
    "calls_spent": ("Gasto de recargas · Llamadas", SensorDeviceClass.MONETARY, "UYU", "mdi:phone"),
    "data_spent": ("Gasto de recargas · Datos", SensorDeviceClass.MONETARY, "UYU", "mdi:web"),
    "sms_spent": ("Gasto de recargas · SMS", SensorDeviceClass.MONETARY, "UYU", "mdi:message-text"),
    "other_spent": ("Gasto de recargas · Otros", SensorDeviceClass.MONETARY, "UYU", "mdi:cash"),
    "calls_used_minutes": ("Minutos hablados de recargas", SensorDeviceClass.DURATION, "min", "mdi:phone-clock"),
    "mobile_data_used_gib": ("Datos usados de recargas", SensorDeviceClass.DATA_SIZE, "GiB", "mdi:download-network"),
    "sms_used_count": ("SMS enviados de recargas", None, None, "mdi:message-text"),
    "download_mbps": ("Velocidad contratada de bajada", SensorDeviceClass.DATA_RATE, "Mbit/s", "mdi:download"),
    "upload_mbps": ("Velocidad contratada de subida", SensorDeviceClass.DATA_RATE, "Mbit/s", "mdi:upload"),
}

DESCRIPTIONS = {
    **METRIC_DESCRIPTIONS,
    "recharge_count": ("Recargas de saldo vigentes", None, None, "mdi:cash-multiple"),
    "free_call_mobile": ("Destinos gratis · Celulares", None, None, "mdi:phone"),
    "free_sms": ("Destinos gratis · SMS", None, None, "mdi:message-text"),
    "free_call_fixed": ("Destinos gratis · Teléfonos fijos", None, None, "mdi:phone-classic"),
    "friend_numbers": ("Números amigos", None, None, "mdi:account-multiple"),
    "balance": ("Saldo", SensorDeviceClass.MONETARY, "UYU", "mdi:cash"),
    "usage_gib": ("Consumo de datos", SensorDeviceClass.DATA_SIZE, "GiB", "mdi:download-network"),
    "allowance_gib": ("Datos incluidos", SensorDeviceClass.DATA_SIZE, "GiB", "mdi:database"),
    "balance_expiry": ("Vencimiento del saldo", SensorDeviceClass.DATE, None, "mdi:calendar-clock"),
    "plan": ("Plan", None, None, "mdi:card-text-outline"),
    "billing_status": ("Estado de facturación", SensorDeviceClass.ENUM, None, "mdi:receipt-text"),
    "pending_count": ("Facturas pendientes", None, None, "mdi:receipt-text-clock"),
    "pending_amount": ("Importe pendiente", SensorDeviceClass.MONETARY, None, "mdi:cash-clock"),
    "next_due": ("Próximo vencimiento", SensorDeviceClass.DATE, None, "mdi:calendar-alert"),
    "last_amount": ("Última factura emitida", SensorDeviceClass.MONETARY, None, "mdi:receipt-text"),
    "last_date": ("Fecha de última factura", SensorDeviceClass.DATE, None, "mdi:calendar"),
}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    known = set()

    def discover():
        entities = []
        for service in coordinator.data.services.values():
            if not coordinator.includes(service.service_id):
                continue
            keys = [
                k
                for k in ("balance", "usage_gib", "allowance_gib", "balance_expiry", "plan")
                if getattr(service, k) is not None
            ]
            if service.destinations is not None:
                keys.extend(k for k in DESTINATION_KEYS if k in service.destinations)
            keys.extend(k for k in METRIC_DESCRIPTIONS if service.metrics.get(k) is not None)
            if service.recharges is not None:
                keys.append("recharge_count")
            if service.billing.status != BillingStatus.NOT_APPLICABLE or service.kind in (
                "tinco",
                "tlk",
            ):
                keys.extend(("billing_status", "pending_count", "pending_amount", "next_due"))
                if coordinator.client.include_history:
                    keys.extend(("last_amount", "last_date"))
            for key in keys:
                identity = service.service_id, key
                if identity not in known:
                    known.add(identity)
                    entities.append(MiAntelSensor(coordinator, entry, service, key))
        if entities:
            async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class MiAntelSensor(MiAntelEntity, SensorEntity):
    def __init__(self, coordinator, entry, service, key):
        super().__init__(coordinator, entry, service, key)
        self.key = key
        _, device_class, unit, icon = DESCRIPTIONS[key]
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        if key in ("usage_gib", "allowance_gib"):
            self._attr_state_class = SensorStateClass.MEASUREMENT
        if key == "billing_status":
            self._attr_options = [status.value for status in BillingStatus]

    @property
    def native_value(self):
        if not self.service:
            return None
        if self.key in DESTINATION_KEYS:
            group = (self.service.destinations or {}).get(self.key)
            return len(group.numbers) if group is not None else None
        if self.key in METRIC_DESCRIPTIONS:
            return self.service.metrics.get(self.key)
        if self.key == "recharge_count":
            return len(self.service.recharges) if self.service.recharges is not None else None
        if self.key == "billing_status":
            return self.service.billing.status.value
        if self.key in ("balance", "usage_gib", "allowance_gib", "balance_expiry", "plan"):
            return getattr(self.service, self.key)
        return getattr(self.service.billing, self.key)

    @property
    def extra_state_attributes(self):
        if self.key == "recharge_count" and self.service and self.service.recharges is not None:
            return {"moneda": "UYU", "recargas": [
                {"saldo": float(r.amount), "vencimiento": r.expires.isoformat()}
                for r in self.service.recharges
            ]}
        if self.key not in DESTINATION_KEYS or not self.service:
            return None
        group = (self.service.destinations or {}).get(self.key)
        if group is None:
            return None
        return {
            "numeros": list(group.numbers),
            "capacidad": group.capacity,
            "lugares_disponibles": group.capacity - len(group.numbers),
        }

    @property
    def native_unit_of_measurement(self):
        if self.service and self.key in ("pending_amount", "last_amount"):
            return (
                self.service.billing.currency
                if self.key == "pending_amount"
                else self.service.billing.last_currency
            )
        return self._attr_native_unit_of_measurement

    @property
    def available(self):
        return super().available and self.native_value is not None
