"""Balance, data and invoice sensors."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass

from .entity import MiAntelEntity
from .web.models import BillingStatus

DESCRIPTIONS = {
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
        if self.key == "billing_status":
            return self.service.billing.status.value
        if self.key in ("balance", "usage_gib", "allowance_gib", "balance_expiry", "plan"):
            return getattr(self.service, self.key)
        return getattr(self.service.billing, self.key)

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
