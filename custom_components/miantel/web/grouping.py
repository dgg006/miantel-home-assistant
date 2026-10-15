"""Explicit service grouping; never infer or combine invoices or readings."""

import hashlib
import json
from dataclasses import dataclass

BILLING_KEYS = frozenset(
    {
        "billing_status",
        "pending_count",
        "pending_amount",
        "next_due",
        "last_amount",
        "last_date",
        "pending",
        "overdue",
    }
)

SPANISH_NAMES = {
    "balance": "Saldo",
    "usage_gib": "Consumo de datos",
    "allowance_gib": "Datos incluidos",
    "balance_expiry": "Vencimiento del saldo",
    "plan": "Plan",
    "billing_status": "Estado de facturación",
    "pending_count": "Cantidad de facturas pendientes",
    "pending_amount": "Importe pendiente",
    "next_due": "Próximo vencimiento",
    "last_amount": "Importe de la última factura",
    "last_date": "Fecha de la última factura",
    "pending": "Facturas pendientes",
    "overdue": "Facturas vencidas",
}


@dataclass(frozen=True, repr=False)
class ServiceGroup:
    name: str
    internet_service: str
    telephone_service: str
    billing_source: str = "separate"

    @property
    def billing_service(self):
        return {"internet": self.internet_service, "telephone": self.telephone_service}.get(
            self.billing_source
        )

    @property
    def group_id(self):
        pair = json.dumps([self.internet_service, self.telephone_service], separators=(",", ":"))
        return hashlib.sha256(pair.encode()).hexdigest()

    @property
    def members(self):
        return self.internet_service, self.telephone_service

    def as_dict(self):
        result = {
            "name": self.name,
            "internet_service": self.internet_service,
            "telephone_service": self.telephone_service,
        }
        if self.billing_source != "separate":
            result["billing_source"] = self.billing_source
        return result


def load_groups(raw):
    if not isinstance(raw, list):
        raise ValueError("Invalid service grouping configuration")
    groups, used = [], set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Invalid service grouping configuration")
        name = item.get("name")
        internet = item.get("internet_service")
        telephone = item.get("telephone_service")
        billing_source = item.get("billing_source", "separate")
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name.strip()) > 100
            or not isinstance(internet, str)
            or not internet.startswith("tinco:srv:")
            or not internet.removeprefix("tinco:srv:")
            or not isinstance(telephone, str)
            or not telephone.startswith("tlk:srv:")
            or not telephone.removeprefix("tlk:srv:")
            or internet in used
            or telephone in used
            or not isinstance(billing_source, str)
            or billing_source not in ("separate", "internet", "telephone")
        ):
            raise ValueError("Invalid service grouping configuration")
        group = ServiceGroup(name.strip(), internet, telephone, billing_source)
        groups.append(group)
        used.update(group.members)
    return tuple(groups)


def group_for(groups, service_id, selected):
    """Keep a group stable during missing readings; both members must be selected."""
    for group in groups:
        if service_id in group.members and (not selected or set(group.members) <= selected):
            return group
    return None


def service_key(account_id, service_id):
    # Preserve the original entity identity when grouping or ungrouping.
    return hashlib.sha256(f"{account_id}:{service_id}".encode()).hexdigest()


def device_details(account_id, service, group=None):
    if group:
        return {
            "key": service_key(account_id, "group:" + group.group_id),
            "name": group.name,
            "model": "Fibra y teléfono fijo",
        }
    return {
        "key": service_key(account_id, service.service_id),
        "name": service.name,
        "model": {
            "acm": "Servicio móvil",
            "tinco": "Servicio de internet",
            "tlk": "Teléfono fijo",
        }.get(service.kind, "Servicio"),
    }


def entity_translation_key(key, service, group=None):
    if group:
        if key in BILLING_KEYS and service.service_id == group.billing_service:
            return "shared_" + key
        return ("internet_" if service.service_id == group.internet_service else "telephone_") + key
    return key


def entity_name(key, service, group=None):
    name = SPANISH_NAMES[key]
    if group:
        if key in BILLING_KEYS and service.service_id == group.billing_service:
            return "Facturación · " + name
        return (
            "Fibra · " if service.service_id == group.internet_service else "Teléfono · "
        ) + name
    return name


def redundant_billing(key, service_id, group=None):
    return bool(
        group
        and group.billing_service
        and key in BILLING_KEYS
        and service_id != group.billing_service
    )
