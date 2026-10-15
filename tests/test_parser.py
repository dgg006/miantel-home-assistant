from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from web import parser
from web.errors import ParseError, SessionExpired
from web.models import Billing, BillingStatus

FIXTURES = Path(__file__).parent / "fixtures"


def sample(name):
    return parser.document((FIXTURES / name).read_bytes())


def test_services_ignore_responsive_duplicate_and_keep_units():
    services = parser.parse_services(sample("services.html"), date(2030, 12, 28))
    assert len(services) == 3
    mobile = services["acm:srv:DEMO-MOVIL"]
    assert mobile.balance == Decimal("42.50")
    assert mobile.balance_expiry == date(2031, 1, 5)
    internet = services["tinco:srv:DEMO-INTERNET"]
    assert internet.usage_gib == Decimal("12.5")
    assert internet.allowance_gib == 200
    assert services["tlk:srv:DEMO-FIJO"].usage_gib is None


def test_service_label_uses_alias_without_scripts_or_repeated_identifier():
    root = sample("services.html")
    alias = root.get_element_by_id("alias-acm-srv-DEMO-MOVIL")
    heading = alias.getparent()
    heading.insert(0, parser.html.fromstring("<span>DEMO-MOVIL</span>"))
    heading.append(
        parser.html.fromstring(
            "<script>servicioACambiarAlias = function(){return PrimeFaces.ab({});};</script>"
        )
    )
    assert (
        parser.parse_services(root, date(2030, 1, 1))["acm:srv:DEMO-MOVIL"].name
        == "Móvil de demostración"
    )


def test_service_label_fallback_ignores_embedded_scripts():
    root = sample("services.html")
    anchor = root.get_element_by_id("s-tlk-srv-DEMO-FIJO")
    anchor.append(parser.html.fromstring("<script>internalFunction();</script>"))
    assert (
        parser.parse_services(root, date(2030, 1, 1))["tlk:srv:DEMO-FIJO"].name
        == "Teléfono de demostración"
    )


def test_partial_service_list_is_not_a_successful_refresh():
    root = sample("services.html")
    root.get_element_by_id("cantServicios").text = "Mis servicios 4"
    with pytest.raises(ParseError, match="incomplete"):
        parser.parse_services(root, date(2030, 1, 1))


def test_initial_zero_header_does_not_hide_loaded_cards():
    root = sample("services.html")
    root.get_element_by_id("cantServicios").text = "Mis servicios 0"
    assert len(parser.parse_services(root, date(2030, 1, 1))) == 3


def test_duplicate_identity_is_rejected():
    root = sample("services.html")
    root.get_element_by_id("s-tlk-srv-DEMO-FIJO").set("id", "s-tinco-srv-DEMO-INTERNET")
    with pytest.raises(ParseError, match="Duplicate"):
        parser.parse_services(root, date(2030, 1, 1))


@pytest.mark.parametrize(
    ("value", "expected"), [("1.234,50", "1234.50"), ("0", "0"), ("42,5", "42.5")]
)
def test_locale_numbers(value, expected):
    assert parser.number(value) == Decimal(expected)


@pytest.mark.parametrize("value", ["unknown", "NaN", "1,2,3", "1.2", ""])
def test_unrecognized_numbers_never_become_zero(value):
    with pytest.raises(ParseError):
        parser.number(value)


def test_expiry_requires_consistent_relative_date():
    assert parser.expiry("Vence el 5 de enero (2 días)", date(2030, 12, 28)) is None
    assert parser.expiry("Vence el 5 de enero", date(2030, 12, 28)) is None


def test_unavailable_is_not_no_debt():
    cards = parser.billing_cards(sample("billing.html"))
    clear = parser.parse_billing_card(cards[0], date(2030, 2, 1))
    failed = parser.parse_billing_card(cards[1], date(2030, 2, 1))
    assert clear.pending_amount == 0 and clear.overdue is False
    assert failed.status == BillingStatus.UNAVAILABLE
    assert failed.pending_amount is None and failed.overdue is None


def pending_table(amounts):
    rows = "".join(f"<tr><td>01/01/2030</td><td>{value}</td></tr>" for value in amounts)
    return parser.document(
        (
            "<div><p>Facturas pendientes</p><table><tr><th>Vencimiento</th><th>Importe</th></tr>"
            + rows
            + "</table></div>"
        ).encode()
    )


def test_pending_invoice_amounts_dates_and_overdue():
    result = parser.parse_billing_card(pending_table(["$ 39,90", "$ 10,00"]), date(2030, 2, 1))
    assert result.status == BillingStatus.PENDING
    assert result.pending_amount == Decimal("49.90")
    assert result.currency == "UYU" and result.pending_count == 2
    assert result.next_due == date(2030, 1, 1) and result.overdue is True


def test_different_currencies_are_not_added_together():
    result = parser.parse_billing_card(pending_table(["$ 39,90", "U$S 5,00"]), date(2030, 2, 1))
    assert result.pending_count == 2 and result.pending_amount is None


def test_unknown_pending_layout_keeps_unknown_amount():
    result = parser.parse_billing_card(
        parser.document(b"<div>Facturas pendientes</div>"), date(2030, 2, 1)
    )
    assert result.status == BillingStatus.PENDING
    assert result.pending_amount is None


def test_invoice_history_does_not_create_debt():
    result = parser.parse_history(
        sample("history.html"), Billing(status=BillingStatus.NO_PENDING, pending_amount=Decimal(0))
    )
    assert result.pending_amount == 0
    assert result.last_amount == 99 and result.last_date == date(2030, 2, 1)


def test_partial_response_encoding_and_expired_view():
    fragment = '<div id="pnlAll"><p>Información ficticia</p></div>'
    body = (
        '<partial-response><changes><update id="pnlAll"><![CDATA['
        + fragment
        + "]]></update></changes></partial-response>"
    ).encode("latin-1")
    assert "Información" in parser.text(parser.partial_document(body))
    with pytest.raises(SessionExpired):
        parser.partial_document(b'<partial-response><redirect url="/login"/></partial-response>')


def test_home_bootstrap_uses_dynamic_component_ids():
    root = parser.document(
        b"""<html><form id="DEMO-form"><input type="hidden" name="javax.faces.ViewState" value="DEMO-state"></form><script>command_demo = function() {return PrimeFaces.ab({s:"DEMO-source",f:"DEMO-form",u:"pnlAll"});};</script></html>"""
    )
    fields = parser.bootstrap(root)
    assert fields["javax.faces.source"] == "DEMO-source"
    assert fields["javax.faces.ViewState"] == "DEMO-state"
