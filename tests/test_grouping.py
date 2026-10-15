import hashlib
from dataclasses import replace
from decimal import Decimal

import pytest
from web.grouping import (
    device_details,
    entity_name,
    entity_translation_key,
    group_for,
    load_groups,
    redundant_billing,
    service_key,
)
from web.models import Billing, BillingStatus, Service

PAIR = {
    "name": "Casa de demostración",
    "internet_service": "tinco:srv:DEMO-INTERNET",
    "telephone_service": "tlk:srv:DEMO-FIJO",
}


def test_manual_pair_shares_device_but_preserves_entities_and_readings():
    (group,) = load_groups([PAIR])
    internet = Service(
        PAIR["internet_service"], "Internet ficticio", "tinco", usage_gib=Decimal("12.5")
    )
    phone = Service(PAIR["telephone_service"], "Teléfono ficticio", "tlk")
    assert device_details("demo-account", internet, group) == device_details(
        "demo-account", phone, group
    )
    assert service_key("demo-account", internet.service_id) != service_key(
        "demo-account", phone.service_id
    )
    assert internet.usage_gib == Decimal("12.5")
    assert phone.usage_gib is None
    assert entity_translation_key("plan", internet, group) == "internet_plan"
    assert entity_translation_key("plan", phone, group) == "telephone_plan"


def test_renaming_group_does_not_change_identity():
    (first,) = load_groups([PAIR])
    renamed = replace(first, name="Otro nombre ficticio")
    assert first.group_id == renamed.group_id


def test_two_pairs_remain_separate_and_accounts_are_isolated():
    other = {
        "name": "Otro lugar ficticio",
        "internet_service": "tinco:srv:DEMO-OTRO-INTERNET",
        "telephone_service": "tlk:srv:DEMO-OTRO-FIJO",
    }
    groups = load_groups([PAIR, other])
    assert groups[0].group_id != groups[1].group_id
    service = Service(PAIR["internet_service"], "Demo", "tinco")
    assert (
        device_details("account-a", service, groups[0])["key"]
        != device_details("account-b", service, groups[0])["key"]
    )


def test_ungrouping_restores_original_device_identity():
    service = Service(PAIR["internet_service"], "Demo", "tinco")
    (group,) = load_groups([PAIR])
    original = hashlib.sha256(f"demo-account:{service.service_id}".encode()).hexdigest()
    assert service_key("demo-account", service.service_id) == original
    assert device_details("demo-account", service)["key"] == original
    assert device_details("demo-account", service, group)["key"] != original
    assert entity_translation_key("plan", service) == "plan"


@pytest.mark.parametrize(
    "raw",
    [
        None,
        {},
        [None],
        [{**PAIR, "name": " "}],
        [{**PAIR, "name": "x" * 101}],
        [{**PAIR, "internet_service": "acm:srv:DEMO-MOVIL"}],
        [{**PAIR, "internet_service": "tinco:srv:"}],
        [{**PAIR, "telephone_service": "tinco:srv:DEMO-OTRO"}],
        [PAIR, {**PAIR, "name": "Duplicado"}],
        [PAIR, {**PAIR, "internet_service": "tinco:srv:DEMO-OTRO"}],
    ],
)
def test_invalid_or_overlapping_groups_are_rejected(raw):
    with pytest.raises(ValueError, match="Invalid service grouping"):
        load_groups(raw)


def test_group_requires_both_selected_services_but_not_both_readings():
    groups = load_groups([PAIR])
    selected = set(groups[0].members)
    assert group_for(groups, PAIR["internet_service"], selected) == groups[0]
    assert group_for(groups, PAIR["internet_service"], {PAIR["internet_service"]}) is None
    assert group_for(groups, "acm:srv:DEMO-MOVIL", selected) is None
    assert group_for([], PAIR["internet_service"], selected) is None


def test_grouping_never_sums_or_coalesces_bills():
    (group,) = load_groups([PAIR])
    first = Service(
        PAIR["internet_service"],
        "Internet ficticio",
        "tinco",
        billing=Billing(status=BillingStatus.PENDING, pending_amount=Decimal("10"), currency="UYU"),
    )
    second = Service(
        PAIR["telephone_service"],
        "Teléfono ficticio",
        "tlk",
        billing=Billing(status=BillingStatus.UNAVAILABLE),
    )
    device_details("demo-account", first, group)
    device_details("demo-account", second, group)
    assert first.billing.pending_amount == Decimal("10")
    assert second.billing.pending_amount is None
    assert first.billing.status != second.billing.status


def test_group_configuration_round_trip_and_empty_default():
    assert load_groups([]) == ()
    (group,) = load_groups([{**PAIR, "name": " Casa de demostración "}])
    assert group.as_dict() == PAIR
    assert load_groups([group.as_dict()]) == (group,)


def test_shared_invoice_uses_explicit_service_without_changing_group_identity():
    (legacy,) = load_groups([PAIR])
    (shared,) = load_groups([{**PAIR, "billing_source": "internet"}])
    assert legacy.billing_service is None
    assert shared.billing_service == PAIR["internet_service"]
    assert shared.group_id == legacy.group_id
    internet = Service(PAIR["internet_service"], "Demo", "tinco")
    telephone = Service(PAIR["telephone_service"], "Demo", "tlk")
    assert entity_translation_key("pending_amount", internet, shared) == "shared_pending_amount"
    assert entity_name("pending_amount", internet, shared) == "Facturación · Importe pendiente"
    assert redundant_billing("pending_amount", telephone.service_id, shared)
    assert not redundant_billing("pending_amount", internet.service_id, shared)
    assert not redundant_billing("usage_gib", telephone.service_id, shared)
    assert not redundant_billing("pending_amount", telephone.service_id, legacy)
    assert load_groups([shared.as_dict()]) == (shared,)


@pytest.mark.parametrize("source", ["wrong", None, True, []])
def test_unsupported_billing_source_is_rejected(source):
    with pytest.raises(ValueError):
        load_groups([{**PAIR, "billing_source": source}])


def test_spanish_names_do_not_depend_on_server_language():
    internet = Service(PAIR["internet_service"], "Demo", "tinco")
    (group,) = load_groups([PAIR])
    assert entity_name("usage_gib", internet, group) == "Fibra · Consumo de datos"
    assert entity_name("pending_count", internet) == "Cantidad de facturas pendientes"
    assert device_details("demo-account", internet, group)["model"] == "Fibra y teléfono fijo"
