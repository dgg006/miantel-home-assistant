"""Run all blocking web work in Home Assistant's executor."""

import logging
from datetime import timedelta

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_GROUPS, CONF_HISTORY, CONF_INTERVAL, CONF_SERVICES, DEFAULT_INTERVAL, DOMAIN
from .web.client import MiAntelClient
from .web.errors import AuthenticationError, ConnectionError, ParseError, RateLimited
from .web.grouping import group_for, load_groups
from .web.models import Snapshot

LOGGER = logging.getLogger(__name__)


class MiAntelCoordinator(DataUpdateCoordinator[Snapshot]):
    def __init__(self, hass, entry):
        self.client = MiAntelClient(
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            include_history=entry.options.get(CONF_HISTORY, False),
        )
        self.selected = set(entry.options.get(CONF_SERVICES, entry.data.get(CONF_SERVICES, [])))
        self.groups = load_groups(entry.options.get(CONF_GROUPS, []))
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL)),
        )

    async def _async_update_data(self):
        try:
            return await self.hass.async_add_executor_job(self.client.fetch)
        except AuthenticationError:
            raise ConfigEntryAuthFailed("MiAntel requiere volver a iniciar sesión") from None
        except RateLimited:
            raise UpdateFailed("MiAntel limitó las consultas", retry_after=900) from None
        except (ConnectionError, ParseError):
            raise UpdateFailed("No se pudieron actualizar los datos de MiAntel") from None

    def includes(self, service_id):
        return not self.selected or service_id in self.selected

    def group_for(self, service_id):
        return group_for(self.groups, service_id, self.selected)
