"""Stable local entities; no account details in public diagnostics."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .web.grouping import (
    device_details,
    entity_name,
    entity_translation_key,
    redundant_billing,
    service_key,
)


class MiAntelEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, service, key):
        super().__init__(coordinator)
        self.service_id = service.service_id
        self._entry = entry
        self._attr_unique_id = f"{service_key(entry.unique_id, service.service_id)}_{key}"
        group = coordinator.group_for(service.service_id)
        self._attr_translation_key = entity_translation_key(key, service, group)
        self._attr_name = entity_name(key, service, group)
        self._attr_entity_registry_visible_default = not redundant_billing(
            key, service.service_id, group
        )
        details = device_details(entry.unique_id, service, group)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, details["key"])},
            name=details["name"],
            manufacturer="Antel",
            model=details["model"],
        )

    @property
    def service(self):
        return self.coordinator.data.services.get(self.service_id)

    @property
    def available(self):
        return super().available and self.service is not None
