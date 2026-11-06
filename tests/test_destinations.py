"""Read-only destination navigation with invented services and numbers."""

import pytest
from test_client import FakeTransport, fixture
from web import parser
from web.client import BILLS, DESTINATIONS, HOME, MiAntelClient, Page
from web.errors import ConnectionError, ParseError, RateLimited


def index(names=("Demo",)):
    cards = "".join(
        f'<div class="icon-card movil"><span id="s-acm-srv-DEMO-{i}">{name}</span>'
        f'<a onclick="mojarra.jsfcljs(document.getElementById(\'nav\'),'
        f'{{\'view-{i}\':\'view-{i}\'}},\'\')">Configurar destinos</a></div>'
        for i, name in enumerate(names)
    )
    return ('<div><h2>Destinos gratis y amigos</h2><form id="nav" '
            'action="/miAntel/app/destinos-gratis-y-amigos/destinos.jsf">'
            '<input type="hidden" name="javax.faces.ViewState" value="FAKE-STATE">'
            + cards + '</form></div>').encode()


def detail(name="Demo", used=1, capacity=2, numbers=("000000001",)):
    infos = "".join(f'<div class="free-destination-info"><span>{n}</span></div>'
                    for n in numbers)
    return (f'<div><h2>{name}</h2><h2>Destinos gratis y amigos</h2>'
            f'<div class="free-destination-row"><div><h4>Amigos con tarifa preferencial '
            f'{used} de {capacity}</h4>{infos}'
            '<div class="modal"><h4>Editar celular</h4><input name="number" value="000000099">'
            '<button name="save">Guardar</button><button name="delete">Eliminar</button></div>'
            '</div></div></div>').encode()


def home(names=("Demo",)):
    cards = "".join(f'<div class="servicioBox"><span id="alias-acm-srv-DEMO-{i}">{name}</span>'
                    '<span class="display-3">10</span></div>' for i,name in enumerate(names))
    return f'<div id="servicesTodos">{cards}</div>'.encode()


def client(pages, **kwargs):
    transport = FakeTransport(pages)
    c = MiAntelClient("demo-user", "demo-password", transport=transport,
                      include_destinations=True, **kwargs)
    return c, transport


def test_destination_numbers_exclude_edit_and_delete_dialogs():
    groups = parser.parse_destinations(parser.document(detail()), "Demo")
    assert groups["friend_numbers"].numbers == ("000000001",)
    assert groups["friend_numbers"].capacity == 2
    assert "000000001" not in repr(groups)


def test_confirmed_empty_group_is_zero_not_unavailable():
    g = parser.parse_destinations(parser.document(detail(used=0,numbers=())), "Demo")
    assert g["friend_numbers"].numbers == ()
    assert g["friend_numbers"].capacity == 2


@pytest.mark.parametrize("body", [detail("Other"), detail(used=2), detail(capacity=0),
    detail(used=2,numbers=("000000001","000000001")), detail(numbers=("unrecognized",))])
def test_wrong_service_or_incomplete_data_is_not_an_empty_list(body):
    with pytest.raises(ParseError):
        parser.parse_destinations(parser.document(body), "Demo")


@pytest.mark.parametrize("title,key", list(parser.DESTINATION_TITLES.items()))
def test_all_four_supported_categories(title, key):
    body = detail().decode().replace("Amigos con tarifa preferencial", title)
    assert key in parser.parse_destinations(parser.document(body.encode()), "Demo")


def test_client_only_submits_list_navigation_command():
    c, t = client([Page(HOME,home()), Page(BILLS,fixture("billing.html")),
        Page(DESTINATIONS,index()), Page(DESTINATIONS,detail())])
    service = c.fetch().services["acm:srv:DEMO-0"]
    assert service.destinations["friend_numbers"].numbers == ("000000001",)
    assert t.calls[-1][1] == {"javax.faces.ViewState":"FAKE-STATE", "view-0":"view-0"}
    assert service.balance == 10


@pytest.mark.parametrize("error", [ConnectionError("Offline"), Page(DESTINATIONS,detail("Other"))])
def test_detail_failure_preserves_balance_and_billing(error):
    c,_ = client([Page(HOME,home()), Page(BILLS,fixture("billing.html")),
        Page(DESTINATIONS,index()), error])
    s=c.fetch()
    assert s.services["acm:srv:DEMO-0"].destinations is None
    assert s.services["acm:srv:DEMO-0"].balance == 10
    assert s.billing_available


def test_selected_mobiles_only_and_fresh_navigation_for_each():
    c,t = client([Page(HOME,home(("Demo","Other"))), Page(BILLS,fixture("billing.html")),
        Page(DESTINATIONS,index(("Demo","Other"))), Page(DESTINATIONS,detail()),
        Page(DESTINATIONS,index(("Demo","Other"))), Page(DESTINATIONS,detail("Other"))])
    s=c.fetch()
    assert all(x.destinations is not None for x in s.services.values())
    assert t.calls[4] == (DESTINATIONS,None,False)
    c,t = client([Page(HOME,home(("Demo","Other"))), Page(BILLS,fixture("billing.html")),
        Page(DESTINATIONS,index(("Demo","Other"))), Page(DESTINATIONS,detail("Other"))],
        destination_services={"acm:srv:DEMO-1"})
    s=c.fetch()
    assert s.services["acm:srv:DEMO-0"].destinations is None
    assert s.services["acm:srv:DEMO-1"].destinations is not None
    assert "view-1" in t.calls[-1][1]


def test_destination_rate_limit_is_not_suppressed():
    c,_ = client([Page(HOME,home()), Page(BILLS,fixture("billing.html")),
        Page(DESTINATIONS,index()), RateLimited("Limited")])
    with pytest.raises(RateLimited):
        c.fetch()
