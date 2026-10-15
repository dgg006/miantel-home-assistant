"""Pending and overdue invoice indicators."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from .entity import MiAntelEntity
from .web.models import BillingStatus


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    known = set()

    def discover():
        entities = []
        for service in coordinator.data.services.values():
            if not coordinator.includes(service.service_id):
                continue
            if service.billing.status == BillingStatus.NOT_APPLICABLE and service.kind not in (
                "tinco",
                "tlk",
            ):
                continue
            for key in ("pending", "overdue"):
                if (service.service_id, key) not in known:
                    known.add((service.service_id, key))
                    entities.append(MiAntelInvoiceFlag(coordinator, entry, service, key))
        if entities:
            async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class MiAntelInvoiceFlag(MiAntelEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, entry, service, key):
        super().__init__(coordinator, entry, service, key)
        self.key = key

    @property
    def is_on(self):
        if not self.service:
            return None
        billing = self.service.billing
        if self.key == "overdue":
            return billing.overdue
        if billing.status == BillingStatus.PENDING:
            return True
        if billing.status == BillingStatus.NO_PENDING:
            return False
        return None

    @property
    def available(self):
        return super().available and self.is_on is not None
