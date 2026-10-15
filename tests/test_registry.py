"""Registry transition unit tests with an in-memory Home Assistant API double."""

import importlib
import itertools
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from web.grouping import group_for, load_groups, service_key
from web.models import Service


class Devices:
    def __init__(self):
        self.items = {}
        self.ids = itertools.count()

    def async_get_or_create(self, **data):
        for device in self.items.values():
            if device.identifiers & data["identifiers"]:
                device.name = data["name"]
                return device
        device = SimpleNamespace(id=f"demo-device-{next(self.ids)}", **data)
        self.items[device.id] = device
        return device

    def async_remove_device(self, device_id):
        del self.items[device_id]


class Entities:
    def __init__(self):
        self.items = {}

    def async_update_entity(self, entity_id, **changes):
        entity = self.items[entity_id]
        for key, value in changes.items():
            setattr(entity, key, value)


@pytest.fixture
def registries(monkeypatch):
    devices, entities = Devices(), Entities()
    # Only the registry module is loaded, not the integration's HA setup.
    modules = {
        name: ModuleType(name)
        for name in [
            "homeassistant",
            "homeassistant.core",
            "homeassistant.helpers",
            "homeassistant.helpers.device_registry",
            "homeassistant.helpers.entity_registry",
            "_miantel_registry_test",
        ]
    }
    modules["homeassistant.core"].callback = lambda function: function
    dr = modules["homeassistant.helpers.device_registry"]
    er = modules["homeassistant.helpers.entity_registry"]
    er.RegistryEntryHider = SimpleNamespace(INTEGRATION="integration", USER="user")
    dr.async_get = lambda hass: devices
    er.async_get = lambda hass: entities
    dr.async_entries_for_config_entry = lambda registry, entry_id: [
        d for d in registry.items.values() if d.config_entry_id == entry_id
    ]
    er.async_entries_for_config_entry = lambda registry, entry_id: [
        e for e in registry.items.values() if e.config_entry_id == entry_id
    ]
    er.async_entries_for_device = lambda registry, device_id, include_disabled_entities=False: [
        e
        for e in registry.items.values()
        if e.device_id == device_id and (include_disabled_entities or not e.disabled_by)
    ]
    modules["_miantel_registry_test"].__path__ = [
        str(Path(__file__).resolve().parents[1] / "custom_components/miantel")
    ]
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    # Reload this module for each independent registry double.
    monkeypatch.delitem(sys.modules, "_miantel_registry_test.registry", raising=False)
    reconcile = importlib.import_module("_miantel_registry_test.registry").async_reconcile_devices
    return devices, entities, reconcile


def context():
    entry = SimpleNamespace(entry_id="demo-entry", unique_id="demo-account")
    internet = Service("tinco:srv:DEMO-INTERNET", "Internet ficticio", "tinco")
    telephone = Service("tlk:srv:DEMO-FIJO", "Teléfono ficticio", "tlk")
    services = {s.service_id: s for s in [internet, telephone]}
    coordinator = SimpleNamespace(
        data=SimpleNamespace(services=services), groups=(), selected=set(services)
    )
    coordinator.includes = lambda service_id: True
    coordinator.group_for = lambda service_id: group_for(
        coordinator.groups, service_id, set(services)
    )
    return entry, coordinator


def add_registered_entities(devices, entities, entry, coordinator):
    for index, service in enumerate(coordinator.data.services.values()):
        key = service_key(entry.unique_id, service.service_id)
        device = next(d for d in devices.items.values() if ("miantel", key) in d.identifiers)
        entity = SimpleNamespace(
            entity_id=f"sensor.demo_{index}",
            config_entry_id=entry.entry_id,
            platform="miantel",
            unique_id=key + "_pending_amount",
            device_id=device.id,
            disabled_by="user" if index else None,
            name="Nombre ficticio del usuario",
            hidden_by=None,
        )
        entities.items[entity.entity_id] = entity


def test_group_and_ungroup_move_disabled_entities_without_changing_ids(registries):
    devices, entities, reconcile = registries
    entry, coordinator = context()
    reconcile(None, entry, coordinator)
    add_registered_entities(devices, entities, entry, coordinator)
    originals = {e.entity_id: (e.unique_id, e.name, e.disabled_by) for e in entities.items.values()}
    coordinator.groups = load_groups(
        [
            {
                "name": "Casa ficticia",
                "internet_service": "tinco:srv:DEMO-INTERNET",
                "telephone_service": "tlk:srv:DEMO-FIJO",
            }
        ]
    )
    reconcile(None, entry, coordinator)
    assert len(devices.items) == 1
    assert len({e.device_id for e in entities.items.values()}) == 1
    coordinator.groups = ()
    reconcile(None, entry, coordinator)
    assert len(devices.items) == 2
    assert len({e.device_id for e in entities.items.values()}) == 2
    assert originals == {
        e.entity_id: (e.unique_id, e.name, e.disabled_by) for e in entities.items.values()
    }


def test_regrouping_with_temporarily_missing_member_keeps_its_entities(registries):
    devices, entities, reconcile = registries
    entry, coordinator = context()
    reconcile(None, entry, coordinator)
    add_registered_entities(devices, entities, entry, coordinator)
    coordinator.groups = load_groups(
        [
            {
                "name": "Casa ficticia",
                "internet_service": "tinco:srv:DEMO-INTERNET",
                "telephone_service": "tlk:srv:DEMO-FIJO",
            }
        ]
    )
    coordinator.data.services.pop("tlk:srv:DEMO-FIJO")
    # The selection still contains the missing service.
    coordinator.group_for = lambda sid: group_for(
        coordinator.groups, sid, set(coordinator.groups[0].members)
    )
    reconcile(None, entry, coordinator)
    assert len({e.device_id for e in entities.items.values()}) == 1
    assert len(entities.items) == 2


def test_ungrouping_with_missing_member_restores_separate_devices(registries):
    devices, entities, reconcile = registries
    entry, coordinator = context()
    reconcile(None, entry, coordinator)
    add_registered_entities(devices, entities, entry, coordinator)
    coordinator.groups = load_groups(
        [
            {
                "name": "Casa ficticia",
                "internet_service": "tinco:srv:DEMO-INTERNET",
                "telephone_service": "tlk:srv:DEMO-FIJO",
            }
        ]
    )
    reconcile(None, entry, coordinator)
    coordinator.data.services.pop("tlk:srv:DEMO-FIJO")
    coordinator.groups = ()
    reconcile(None, entry, coordinator)
    assert len(devices.items) == 2
    assert len({e.device_id for e in entities.items.values()}) == 2


def test_unrelated_device_is_not_removed(registries):
    devices, entities, reconcile = registries
    entry, coordinator = context()
    unrelated = devices.async_get_or_create(
        config_entry_id="another-entry", identifiers={("another-domain", "demo")}, name="Other"
    )
    reconcile(None, entry, coordinator)
    assert unrelated.id in devices.items


def test_shared_billing_hides_only_duplicate_and_restores_on_separation(registries):
    devices, entities, reconcile = registries
    entry, coordinator = context()
    reconcile(None, entry, coordinator)
    add_registered_entities(devices, entities, entry, coordinator)
    (group,) = load_groups(
        [
            {
                "name": "Casa ficticia",
                "internet_service": "tinco:srv:DEMO-INTERNET",
                "telephone_service": "tlk:srv:DEMO-FIJO",
                "billing_source": "internet",
            }
        ]
    )
    coordinator.groups = (group,)
    reconcile(None, entry, coordinator)
    assert entities.items["sensor.demo_0"].hidden_by is None
    assert entities.items["sensor.demo_1"].hidden_by == "integration"
    coordinator.groups = ()
    reconcile(None, entry, coordinator)
    assert all(e.hidden_by is None for e in entities.items.values())


def test_shared_billing_does_not_override_user_hidden_setting(registries):
    devices, entities, reconcile = registries
    entry, coordinator = context()
    reconcile(None, entry, coordinator)
    add_registered_entities(devices, entities, entry, coordinator)
    entities.items["sensor.demo_1"].hidden_by = "user"
    coordinator.groups = load_groups(
        [
            {
                "name": "Casa ficticia",
                "internet_service": "tinco:srv:DEMO-INTERNET",
                "telephone_service": "tlk:srv:DEMO-FIJO",
                "billing_source": "internet",
            }
        ]
    )
    reconcile(None, entry, coordinator)
    coordinator.groups = ()
    reconcile(None, entry, coordinator)
    assert entities.items["sensor.demo_1"].hidden_by == "user"
