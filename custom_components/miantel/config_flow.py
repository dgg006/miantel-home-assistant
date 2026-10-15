"""Local configuration, account validation and reauthentication."""

import hashlib

import probatio as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_GROUPS,
    CONF_HISTORY,
    CONF_INTERVAL,
    CONF_SERVICES,
    DEFAULT_INTERVAL,
    DOMAIN,
    MAX_INTERVAL,
    MIN_INTERVAL,
)
from .web.client import MiAntelClient
from .web.errors import (
    AdditionalAuthenticationRequired,
    AuthenticationError,
    ConnectionError,
    ParseError,
    RateLimited,
)
from .web.grouping import load_groups


def billing_source_selector():
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                {"value": "separate", "label": "Facturas separadas"},
                {"value": "internet", "label": "Factura compartida: consultar desde la fibra"},
                {"value": "telephone", "label": "Factura compartida: consultar desde el teléfono"},
            ]
        )
    )


def account_key(username):
    return hashlib.sha256(username.strip().encode()).hexdigest()


def credentials_schema(username=""):
    return vol.Schema(
        {vol.Required(CONF_USERNAME, default=username): str, vol.Required(CONF_PASSWORD): str}
    )


def validate(data):
    client = MiAntelClient(data[CONF_USERNAME], data[CONF_PASSWORD])
    try:
        return client.fetch()
    finally:
        client.close()


class MiAntelConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _validate(self, data):
        try:
            snapshot = await self.hass.async_add_executor_job(validate, data)
            if not snapshot.services:
                return None, "no_services"
            return snapshot, None
        except AdditionalAuthenticationRequired:
            return None, "additional_auth"
        except AuthenticationError:
            return None, "invalid_auth"
        except RateLimited:
            return None, "rate_limited"
        except ConnectionError:
            return None, "cannot_connect"
        except ParseError:
            return None, "unsupported_response"

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            snapshot, error = await self._validate(user_input)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(account_key(user_input[CONF_USERNAME]))
                self._abort_if_unique_id_configured()
                self._credentials = dict(user_input)
                self._services = snapshot.services
                return await self.async_step_services()
        return self.async_show_form(step_id="user", data_schema=credentials_schema(), errors=errors)

    async def async_step_services(self, user_input=None):
        errors = {}
        if user_input is not None:
            selected = user_input.get(CONF_SERVICES, [])
            if not selected:
                errors["base"] = "select_service"
            elif not set(selected) <= self._services.keys():
                errors["base"] = "select_service"
            else:
                return self.async_create_entry(
                    title="MiAntel", data={**self._credentials, CONF_SERVICES: selected}
                )
        choices = [{"value": key, "label": service.name} for key, service in self._services.items()]
        schema = vol.Schema(
            {
                vol.Required(CONF_SERVICES, default=list(self._services)): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=choices, multiple=True)
                )
            }
        )
        return self.async_show_form(step_id="services", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            _, error = await self._validate(user_input)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(account_key(user_input[CONF_USERNAME]))
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=credentials_schema(entry.data[CONF_USERNAME]),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return MiAntelOptionsFlow()


class MiAntelOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        runtime = getattr(self.config_entry, "runtime_data", None)
        if runtime is None or runtime.data is None:
            return self.async_abort(reason="not_loaded")
        self._services = runtime.data.services
        if user_input is not None:
            selected = user_input.get(CONF_SERVICES, [])
            if not selected or not set(selected) <= self._services.keys():
                return self.async_show_form(
                    step_id="init", data_schema=self._schema(), errors={"base": "select_service"}
                )
            self._pending = {
                key: value for key, value in user_input.items() if key != "manage_groups"
            }
            self._groups = list(load_groups(self.config_entry.options.get(CONF_GROUPS, [])))
            if user_input.get("manage_groups"):
                return await self.async_step_groups()
            return await self.async_step_finish()
        return self.async_show_form(step_id="init", data_schema=self._schema())

    def _schema(self):
        options = self.config_entry.options
        services = self._services
        choices = [{"value": key, "label": service.name} for key, service in services.items()]
        selected = options.get(
            CONF_SERVICES, self.config_entry.data.get(CONF_SERVICES, list(services))
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SERVICES, default=[key for key in selected if key in services]
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=choices, multiple=True)
                ),
                vol.Required(
                    CONF_INTERVAL, default=options.get(CONF_INTERVAL, DEFAULT_INTERVAL)
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_INTERVAL, max=MAX_INTERVAL)),
                vol.Required(CONF_HISTORY, default=options.get(CONF_HISTORY, False)): bool,
                vol.Required("manage_groups", default=False): bool,
            }
        )
        return schema

    def _choices(self, kind):
        used = {member for group in self._groups for member in group.members}
        selected = set(self._pending[CONF_SERVICES])
        return [
            {"value": key, "label": service.name}
            for key, service in self._services.items()
            if key in selected and key not in used and service.kind == kind
        ]

    async def async_step_groups(self, user_input=None):
        menu = []
        if self._choices("tinco") and self._choices("tlk"):
            menu.append("add_group")
        if self._groups:
            menu.append("edit_group")
            menu.append("remove_group")
        menu.append("finish")
        return self.async_show_menu(
            step_id="groups",
            menu_options=menu,
            description_placeholders={"count": str(len(self._groups))},
        )

    async def async_step_add_group(self, user_input=None):
        internet = self._choices("tinco")
        telephone = self._choices("tlk")
        if not internet or not telephone:
            return await self.async_step_groups()
        errors = {}
        if user_input is not None:
            try:
                if user_input["internet_service"] not in {
                    v["value"] for v in internet
                } or user_input["telephone_service"] not in {v["value"] for v in telephone}:
                    raise ValueError("Invalid service pair")
                raw = [group.as_dict() for group in self._groups]
                raw.append(
                    {
                        "name": user_input["group_name"],
                        "internet_service": user_input["internet_service"],
                        "telephone_service": user_input["telephone_service"],
                        "billing_source": user_input.get("billing_source", "separate"),
                    }
                )
                self._groups = list(load_groups(raw))
            except (KeyError, ValueError):
                errors["base"] = "invalid_group"
            else:
                return await self.async_step_groups()
        schema = vol.Schema(
            {
                vol.Required("group_name"): vol.All(str, vol.Length(min=1, max=100)),
                vol.Required("internet_service"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=internet)
                ),
                vol.Required("telephone_service"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=telephone)
                ),
                vol.Required("billing_source", default="separate"): billing_source_selector(),
            }
        )
        return self.async_show_form(step_id="add_group", data_schema=schema, errors=errors)

    async def async_step_edit_group(self, user_input=None):
        if not self._groups:
            return await self.async_step_groups()
        errors = {}
        if user_input is not None:
            group_id = user_input.get("group_id")
            if any(group.group_id == group_id for group in self._groups):
                self._editing_group = group_id
                return await self.async_step_group_settings()
            errors["base"] = "select_group"
        choices = [{"value": group.group_id, "label": group.name} for group in self._groups]
        schema = vol.Schema(
            {
                vol.Required("group_id"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=choices)
                )
            }
        )
        return self.async_show_form(step_id="edit_group", data_schema=schema, errors=errors)

    async def async_step_group_settings(self, user_input=None):
        current = next(group for group in self._groups if group.group_id == self._editing_group)
        errors = {}
        if user_input is not None:
            try:
                raw = [group.as_dict() for group in self._groups]
                index = self._groups.index(current)
                raw[index] = {
                    **current.as_dict(),
                    "name": user_input["group_name"],
                    "billing_source": user_input["billing_source"],
                }
                self._groups = list(load_groups(raw))
            except (KeyError, ValueError):
                errors["base"] = "invalid_group"
            else:
                return await self.async_step_groups()
        schema = vol.Schema(
            {
                vol.Required("group_name", default=current.name): vol.All(
                    str, vol.Length(min=1, max=100)
                ),
                vol.Required(
                    "billing_source", default=current.billing_source
                ): billing_source_selector(),
            }
        )
        return self.async_show_form(step_id="group_settings", data_schema=schema, errors=errors)

    async def async_step_remove_group(self, user_input=None):
        if not self._groups:
            return await self.async_step_groups()
        errors = {}
        if user_input is not None:
            removed = set(user_input.get("groups_to_remove", []))
            if removed and removed <= {group.group_id for group in self._groups}:
                self._groups = [group for group in self._groups if group.group_id not in removed]
                return await self.async_step_groups()
            errors["base"] = "select_group"
        choices = [{"value": group.group_id, "label": group.name} for group in self._groups]
        schema = vol.Schema(
            {
                vol.Required("groups_to_remove"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=choices, multiple=True)
                )
            }
        )
        return self.async_show_form(step_id="remove_group", data_schema=schema, errors=errors)

    async def async_step_finish(self, user_input=None):
        return self.async_create_entry(
            title="",
            data={**self._pending, CONF_GROUPS: [group.as_dict() for group in self._groups]},
        )
