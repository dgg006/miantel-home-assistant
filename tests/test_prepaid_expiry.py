"""Synthetic recharge views; no account data or captured HTML."""

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from test_client import FakeTransport, fixture
from web import parser
from web.client import BILLS, HOME, LOCAL_ZONE, MiAntelClient, Page
from web.errors import ConnectionError, ParseError, RateLimited


def detail(name="Demo", labels=("Vence el 5 de enero (8 días)",), kind="Recarga saldo"):
    cards = "".join(
        f'<div class="mini-card-recarga"><div class="card-header"><p>{kind}</p>'
        f'<p>{label}</p></div></div>' for label in labels
    )
    return f"<div><h2>{name}</h2><h2>Detalle de mi consumo</h2>{cards}</div>".encode()


def home(names=("Demo",), instruction=True):
    message = "Para ver vencimiento de las recargas vaya a Ver detalle del consumo"
    cards = "".join(
        f'<div class="servicioBox"><h5 id="alias-acm-srv-DEMO-{i}">{name}</h5>'
        '<span class="display-3">10</span>'
        f'<p>{message if instruction else "Servicio con contrato"}</p>'
        f'<form id="demo-{i}" action="/miAntel/">'
        '<input type="hidden" name="javax.faces.ViewState" value="OLD">'
        f'<a onclick="mojarra.jsfcljs(document.getElementById(\'demo-{i}\'),'
        f'{{\'read-{i}\':\'read-{i}\'}},\'\')">Ver detalle del consumo</a></form></div>'
        for i, name in enumerate(names)
    )
    return f'<div id="servicesTodos">{cards}</div>'.encode()


def client(monkeypatch, pages):
    monkeypatch.setattr("web.client.datetime", SimpleNamespace(
        now=lambda zone: datetime(2030, 12, 28, 12, tzinfo=LOCAL_ZONE)))
    transport = FakeTransport(pages)
    return MiAntelClient("demo-user", "demo-password", transport=transport), transport


def test_recharges_choose_earliest_date_across_year():
    root = parser.document(detail(labels=(
        "Vence el 10 de enero (13 días)", "Vence el 5 de enero (8 días)")))
    assert parser.parse_prepaid_expiry(root, date(2030, 12, 28), "Demo") == date(2031, 1, 5)


def test_consumption_rejects_another_mobile():
    with pytest.raises(ParseError):
        parser.parse_prepaid_expiry(parser.document(detail("Other")), date(2030, 12, 28), "Demo")


def test_data_packages_and_no_active_recharges_have_no_balance_expiry():
    assert parser.parse_prepaid_expiry(
        parser.document(detail(kind="Recarga datos")), date(2030, 12, 28), "Demo") is None
    assert parser.parse_prepaid_expiry(
        parser.document(detail(labels=())), date(2030, 12, 28), "Demo") is None


@pytest.mark.parametrize("label", ["Vence el 5 de enero (1 día)", "Vence el 5 de enero", "Vencido"])
def test_unknown_date_never_produces_a_guessed_expiry(label):
    with pytest.raises(ParseError):
        parser.parse_prepaid_expiry(
            parser.document(detail(labels=(label,))), date(2030, 12, 28), "Demo")


@pytest.mark.parametrize("missing_field", [False, True])
def test_partial_response_updates_navigation_viewstate(missing_field):
    content = home()
    if missing_field:
        content = content.replace(b'<input type="hidden" name="javax.faces.ViewState" value="OLD">', b"")
    body = (b'<partial-response><changes><update id="pnlAll"><![CDATA[' + content
            + b']]></update><update id="javax.faces.ViewState"><![CDATA[FRESH]]>'
            b'</update></changes></partial-response>')
    root = parser.partial_document(body)
    link = parser.prepaid_detail_links(root)["acm:srv:DEMO-0"]
    _, fields = parser.link_submission(root, link)
    assert fields["javax.faces.ViewState"] == "FRESH"


def test_fetch_reads_prepaid_expiry_and_keeps_billing(monkeypatch):
    c, transport = client(monkeypatch, [Page(HOME, home()),
        Page(HOME + "consumo/movil", detail()), Page(BILLS, fixture("billing.html"))])
    service = c.fetch().services["acm:srv:DEMO-0"]
    assert service.balance == 10
    assert service.balance_expiry == date(2031, 1, 5)
    assert len(transport.calls) == 3


def test_two_prepaids_reload_view_before_next_navigation(monkeypatch):
    c, transport = client(monkeypatch, [Page(HOME, home(("Demo", "Other"))),
        Page(HOME + "consumo/movil", detail()), Page(HOME, home(("Demo", "Other"))),
        Page(HOME + "consumo/movil", detail("Other")), Page(BILLS, fixture("billing.html"))])
    services = c.fetch().services
    assert all(s.balance_expiry == date(2031, 1, 5) for s in services.values())
    assert transport.calls[2] == (HOME, None, False)
    assert "read-1" in transport.calls[3][1]


@pytest.mark.parametrize("response", [ConnectionError("Offline"),
    Page(HOME + "consumo/movil", detail("Wrong mobile"))])
def test_detail_failure_preserves_balance_and_billing(monkeypatch, response):
    c, _ = client(monkeypatch, [Page(HOME, home()), response,
        Page(BILLS, fixture("billing.html"))])
    snapshot = c.fetch()
    assert snapshot.services["acm:srv:DEMO-0"].balance == 10
    assert snapshot.services["acm:srv:DEMO-0"].balance_expiry is None
    assert snapshot.billing_available


def test_contract_without_prepaid_instruction_is_not_queried(monkeypatch):
    c, transport = client(monkeypatch, [Page(HOME, home(instruction=False)),
        Page(BILLS, fixture("billing.html"))])
    assert c.fetch().services["acm:srv:DEMO-0"].balance_expiry is None
    assert len(transport.calls) == 2


def test_prepaid_detail_rate_limit_stops_queries(monkeypatch):
    c, transport = client(monkeypatch, [Page(HOME, home()), RateLimited("Limited")])
    with pytest.raises(RateLimited):
        c.fetch()
    assert len(transport.calls) == 2
