"""Diagnostics contain only operational metadata, never account records."""

from .const import CONF_HISTORY, CONF_INTERVAL, DEFAULT_INTERVAL, VERSION


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = getattr(entry, "runtime_data", None)
    return {
        "version": VERSION,
        "scan_interval_minutes": entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL),
        "include_history": entry.options.get(CONF_HISTORY, False),
        "last_update_success": bool(coordinator and coordinator.last_update_success),
        "billing_available": bool(
            coordinator and coordinator.data and coordinator.data.billing_available
        ),
    }
