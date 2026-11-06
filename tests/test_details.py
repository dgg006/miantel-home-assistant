"""Synthetic, read-only extended detail views. Never use captured account HTML."""

from datetime import date
from decimal import Decimal

import pytest
from test_client import FakeTransport, fixture
from web import details, parser
from web.client import BILLS, HOME, MiAntelClient, Page
from web.errors import ConnectionError, ParseError, RateLimited
from web.models import Service


def root(body):
    return parser.document(body.encode())


def view(body="", title="Detalle de mi consumo", name="Demo"):
    return root(f"<div><h2>{name}</h2><h2>{title}</h2>{body}</div>")


def cycle_body(start="1 de diciembre", end="31 de diciembre", days=4):
    return f"<p>Ciclo actual: {start} al {end}</p><p>Quedan {days} días para renovar</p>"


def recharge(amount="12,50", label="Vence el 5 de enero (8 días)"):
    return (
        '<div class="mini-card-recarga"><div class="card-header">'
        f'<p>Recarga saldo</p><p>{label}</p></div><div class="card-body">'
        f"<small>$</small><span>{amount}</span></div></div>"
    )


def spend(category="Llamadas", money="$10", equivalent="2 min."):
    return (
        '<div class="CombouseMiPlanMobile"><div>'
        f"<p>{category}</p><p>Consumido</p><strong>{money}</strong></div>"
        f"<div><p>Equivalente a</p><strong>{equivalent}</strong></div></div>"
    )


def speed_card(down="400", up="40", current=True):
    return (
        '<div class="card-planes">'
        f"<p>{down}/{up} Mbps de velocidad</p>"
        + ("<span>Tu plan actual</span>" if current else "<a>Cambiar a este plan</a>")
        + "</div>"
    )


def test_cycle_requires_current_period_and_consistent_renewal():
    m = details.cycle(view(cycle_body()), date(2030, 12, 28))
    assert m == {
        "cycle_start": date(2030, 12, 1),
        "cycle_end": date(2030, 12, 31),
        "renewal_date": date(2031, 1, 1),
        "renewal_days": 4,
    }
    with pytest.raises(ParseError):
        details.cycle(view(cycle_body(days=24)), date(2030, 12, 28))


def test_cycle_infers_year_across_december_january():
    m = details.cycle(view(cycle_body("20 de diciembre", "19 de enero", 22)), date(2030, 12, 29))
    assert m["cycle_start"] == date(2030, 12, 20)
    assert m["cycle_end"] == date(2031, 1, 19)
    assert m["renewal_date"] == date(2031, 1, 20)


@pytest.mark.parametrize(
    "body",
    [
        cycle_body("31 de noviembre"),
        cycle_body("1 de unknown"),
        cycle_body() + cycle_body("2 de noviembre"),
        "<p>Quedan 25 días para renovar</p>",
    ],
)
def test_invalid_cycle_never_becomes_guessed_dates(body):
    with pytest.raises(ParseError):
        details.cycle(view(body), date(2030, 12, 28))


def test_recharge_details_keep_each_balance_and_sort_expiry():
    rs = details.recharges(
        view(recharge() + recharge("3", "Vence el 29 de diciembre (1 día)")), date(2030, 12, 28)
    )
    assert [r.amount for r in rs] == [Decimal("3"), Decimal("12.50")]
    assert rs[0].expires == date(2030, 12, 29)


def test_monthly_plan_without_recharges_is_not_zero():
    assert details.recharges(view(), date(2030, 12, 28)) is None
    assert details.recharges(view("<p>No tenés recargas activas</p>"), date(2030, 12, 28)) == ()


@pytest.mark.parametrize(
    "body",
    [
        recharge("-1"),
        recharge(label="Vence el 5 de enero"),
        recharge().replace("<small>$</small>", "<small>USD</small>"),
    ],
)
def test_invalid_recharge_data_is_not_replaced_with_zero(body):
    with pytest.raises(ParseError):
        details.recharges(view(body), date(2030, 12, 28))


def test_spending_retains_money_and_independent_units():
    m = details.spending(
        view(spend() + spend("Datos", "$2,50", "512 MB") + spend("SMS", "$1", "3 SMS"))
    )
    assert m["calls_spent"] == 10 and m["calls_used_minutes"] == 2
    assert m["data_spent"] == Decimal("2.50") and m["mobile_data_used_gib"] == Decimal("0.5")
    assert m["sms_spent"] == 1 and m["sms_used_count"] == 3


@pytest.mark.parametrize(
    "body",
    [
        spend(equivalent="2 GB"),
        spend(equivalent="unknown"),
        spend(money="USD10"),
        spend() + spend(),
        spend("SMS", equivalent="1,5 SMS"),
    ],
)
def test_unrecognized_spending_does_not_guess_quantities(body):
    with pytest.raises(ParseError):
        details.spending(view(body))


def test_one_invalid_section_keeps_other_independent_details():
    m, rs = details.consumption(
        view(cycle_body(days=1) + spend() + recharge()), "Demo", date(2030, 12, 28), mobile=True
    )
    assert "cycle_start" not in m
    assert m["calls_spent"] == 10
    assert len(rs) == 1


@pytest.mark.parametrize("method", ["consumption", "roaming"])
def test_detail_is_scoped_to_the_requested_service(method):
    with pytest.raises(ParseError):
        if method == "consumption":
            details.consumption(view(name="Other"), "Demo", date(2030, 12, 28), mobile=True)
        else:
            details.roaming(view(title="Roaming internacional", name="Other"), "Demo")


@pytest.mark.parametrize("checked,expected", [(" checked", True), ("", False)])
def test_roaming_checked_and_unchecked_are_both_valid_states(checked, expected):
    r = view(f'<input type="checkbox" name="switchTest"{checked}>', title="Roaming internacional")
    assert details.roaming(r, "Demo") is expected
    assert details.roaming(r, "Demo") == expected  # Reading the DOM never submits the checkbox.


def test_missing_or_duplicate_roaming_controls_are_unavailable():
    for body in ["", '<input type="checkbox" name="switchTest">' * 2]:
        with pytest.raises(ParseError):
            details.roaming(view(body, title="Roaming internacional"), "Demo")


def test_contracted_speed_ignores_faster_offered_plans():
    r = root(
        "<div><h2>Mejorar plan</h2>" + speed_card() + speed_card("900", "900", False) + "</div>"
    )
    assert details.plan_speed(r) == {"download_mbps": 400, "upload_mbps": 40}


@pytest.mark.parametrize(
    "body",
    [
        speed_card(current=False),
        speed_card() + speed_card(),
        speed_card("0"),
        speed_card("unknown"),
    ],
)
def test_unknown_current_plan_is_not_replaced_by_an_offer(body):
    with pytest.raises(ParseError):
        details.plan_speed(root("<div><h2>Mejorar plan</h2>" + body + "</div>"))


def home():
    return (
        b'<div id="servicesTodos"><div class="servicioBox">'
        b'<span id="alias-acm-srv:DEMO">Demo</span></div></div>'
    )


def test_client_extended_reads_keep_balance_and_never_submit_management_fields():
    body = fixture("services.html")
    # Only this mobile is selected for extra queries; no fiber plan navigation occurs.
    c = MiAntelClient(
        "demo-user",
        "demo-password",
        include_details=True,
        destination_services={"acm:srv:DEMO-MOVIL"},
    )
    calls = []

    def navigate(key, labels, root=None):
        calls.append((key, labels))
        if labels == ("roaming",):
            return view(
                '<input type="checkbox" name="switchTest">',
                title="Roaming internacional",
                name="Móvil de demostración",
            )
        return view(spend() + recharge(), name="Móvil de demostración")

    c._navigate_service = navigate
    c._transport = FakeTransport([Page(HOME, body), Page(BILLS, fixture("billing.html"))])
    s = c.fetch().services["acm:srv:DEMO-MOVIL"]
    assert s.metrics["roaming_enabled"] is False and s.metrics["calls_spent"] == 10
    assert s.balance is not None
    assert len(calls) == 2 and all(k == s.service_id for k, _ in calls)


def test_speed_cache_expires_and_is_invalidated_on_plan_change(monkeypatch):
    clock = [0]
    monkeypatch.setattr("web.client.monotonic", lambda: clock[0])
    c = MiAntelClient("demo-user", "demo-password", include_details=True)
    calls = []
    c._navigate_service = lambda key, labels: (
        calls.append(labels) or root("<div><h2>Mejorar plan</h2>" + speed_card() + "</div>")
    )
    services = {"tinco:srv:DEMO": Service("tinco:srv:DEMO", "Demo", "tinco", plan="Demo plan")}
    c._read_extra_views(services)
    c._read_extra_views(services)
    assert len(calls) == 1
    clock[0] = 86401
    c._read_extra_views(services)
    assert len(calls) == 2
    services["tinco:srv:DEMO"] = Service("tinco:srv:DEMO", "Demo", "tinco", plan="Other plan")
    c._read_extra_views(services)
    assert len(calls) == 3


@pytest.mark.parametrize("error", [ConnectionError("Offline"), ParseError("Changed")])
def test_extra_failure_keeps_preexisting_readings(error):
    c = MiAntelClient("demo-user", "demo-password", include_details=True)

    def fail(*args, **kwargs):
        raise error

    c._navigate_service = fail
    s = Service("acm:srv:DEMO", "Demo", "acm", balance=Decimal("10"))
    services = {s.service_id: s}
    c._read_extra_views(services)
    assert services[s.service_id].balance == 10 and not services[s.service_id].metrics


def test_extra_rate_limit_is_propagated():
    c = MiAntelClient("demo-user", "demo-password", include_details=True)

    def fail(*args, **kwargs):
        raise RateLimited("Limited")

    c._navigate_service = fail
    with pytest.raises(RateLimited):
        c._read_extra_views({"acm:srv:DEMO": Service("acm:srv:DEMO", "Demo", "acm")})
