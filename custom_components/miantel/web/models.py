"""Typed account data; never used as diagnostics or log messages."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class BillingStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    NO_PENDING = "no_pending"
    PENDING = "pending"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Billing:
    status: BillingStatus = BillingStatus.NOT_APPLICABLE
    pending_count: int | None = None
    pending_amount: Decimal | None = None
    currency: str | None = None
    next_due: date | None = None
    overdue: bool | None = None
    last_amount: Decimal | None = None
    last_currency: str | None = None
    last_date: date | None = None
    history_available: bool = False


@dataclass(frozen=True)
class Service:
    service_id: str = field(repr=False)
    name: str = field(repr=False)
    kind: str
    plan: str | None = field(default=None, repr=False)
    balance: Decimal | None = None
    usage_gib: Decimal | None = None
    allowance_gib: Decimal | None = None
    balance_expiry: date | None = None
    billing: Billing = field(default_factory=Billing)


@dataclass(frozen=True)
class Snapshot:
    services: dict[str, Service] = field(repr=False)
    updated_at: datetime
    billing_available: bool = True
