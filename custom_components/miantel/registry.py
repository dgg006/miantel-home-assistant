"""Move existing entities between devices without changing entity identities."""

import re

from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .web.grouping import device_details, redundant_billing, service_key
from .web.models import Service


@callback
def async_reconcile_devices(hass, entry, coordinator):
    devices = dr.async_get(hass)
    entities = er.async_get(hass)
    old_devices = list(dr.async_entries_for_config_entry(devices, entry.entry_id))
    targets = {}
    identities = {}
    services = dict(coordinator.data.services)
    # A temporary failed/missing card must not trap its existing entities in an old group.
    for service_id in coordinator.selected:
        if service_id not in services:
            kind = service_id.split(":")[0]
            services[service_id] = Service(service_id, "Antel", kind)
    for service in services.values():
        if not coordinator.includes(service.service_id):
            continue
        group = coordinator.group_for(service.service_id)
        details = device_details(entry.unique_id, service, group)
        if service.service_id not in coordinator.data.services and group is None:
            previous = next(
                (
                    device
                    for device in old_devices
                    if (DOMAIN, details["key"]) in device.identifiers
                ),
                None,
            )
            if previous and previous.name:
                details["name"] = previous.name
        device = devices.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, details["key"])},
            name=details["name"],
            manufacturer="Antel",
            model=details["model"],
        )
        members = group.members if group else (service.service_id,)
        for member in members:
            targets[service_key(entry.unique_id, member)] = device.id
            identities[service_key(entry.unique_id, member)] = member
    # Includes disabled entities, preserving their settings and identifiers too.
    for entity in er.async_entries_for_config_entry(entities, entry.entry_id):
        identity, _, key = entity.unique_id.partition("_")
        if (
            entity.platform == DOMAIN
            and identity in targets
            and entity.device_id != targets[identity]
        ):
            entities.async_update_entity(entity.entity_id, device_id=targets[identity])
        if entity.platform == DOMAIN and identity in identities:
            member = identities[identity]
            redundant = redundant_billing(key, member, coordinator.group_for(member))
            if redundant and entity.hidden_by is None:
                entities.async_update_entity(
                    entity.entity_id, hidden_by=er.RegistryEntryHider.INTEGRATION
                )
            elif not redundant and entity.hidden_by == er.RegistryEntryHider.INTEGRATION:
                entities.async_update_entity(entity.entity_id, hidden_by=None)
    for device in old_devices:
        # Leave devices from other integrations and any device still in use alone.
        if device.id in targets.values() or device.config_entry_id != entry.entry_id:
            continue
        if not any(
            domain == DOMAIN and re.fullmatch(r"[0-9a-f]{64}", value)
            for domain, value in device.identifiers
        ):
            continue
        if not er.async_entries_for_device(entities, device.id, include_disabled_entities=True):
            devices.async_remove_device(device.id)
