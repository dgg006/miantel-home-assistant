from pathlib import Path
from urllib.error import URLError

import pytest
from web.client import BILLS, HOME, HttpTransport, MiAntelClient, Page, validate_url
from web.errors import (
    AdditionalAuthenticationRequired,
    AuthenticationError,
    ConnectionError,
    ParseError,
    RateLimited,
    SessionExpired,
)
from web.models import BillingStatus

FIXTURES = Path(__file__).parent / "fixtures"
IDP = "https://eidas.tuid.uy/"
SELECTOR = b"""<form id="flowSelectorForm" action="/select"><input type="hidden" name="javax.faces.ViewState" value="FAKE-STATE"><a onclick="mojarra.jsfcljs(document.getElementById('flowSelectorForm'),{'select-demo':'select-demo'},'')">Usuario y contrase\xc3\xb1a</a></form>"""
USER = b'<form action="/username"><input name="userIdentifier"><input type="submit" name="continue"></form>'
PASSWORD = b'<form action="/password"><input type="password" name="password"><input type="submit" name="continue"></form>'
RELAY = b'<form action="/relay"><input type="hidden" name="response" value="FAKE-RELAY"></form>'
SHELL = b"""<html><body id="bodyMiAntel"><div id="pnlAll"></div><form id="home-demo"><input type="hidden" name="javax.faces.ViewState" value="FAKE-HOME"></form><script>command_demo = function() {return PrimeFaces.ab({s:"load-demo",f:"home-demo",u:"pnlAll"});};</script></body></html>"""


def fixture(name):
    return (FIXTURES / name).read_bytes()


def partial():
    content = fixture("services.html").decode()
    return (
        '<partial-response><changes><update id="pnlAll"><![CDATA['
        + content
        + "]]></update></changes></partial-response>"
    ).encode()


class FakeTransport:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []
        self.clears = 0

    def clear(self):
        self.clears += 1

    def request(self, url, fields=None, *, ajax=False):
        self.calls.append((url, fields, ajax))
        item = self.pages.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def login_pages():
    return [
        Page(IDP + "select", SELECTOR),
        Page(IDP + "username", USER),
        Page(IDP + "relay", RELAY),
        Page(IDP + "password", PASSWORD),
        Page(IDP + "relay", RELAY),
        Page(HOME, SHELL),
    ]


def test_expired_session_logs_in_and_loads_services_and_billing():
    transport = FakeTransport(
        [
            Page(IDP, SELECTOR),
            *login_pages(),
            Page(HOME, SHELL),
            Page(HOME, partial()),
            Page(BILLS, fixture("billing.html")),
        ]
    )
    snapshot = MiAntelClient("demo-user", "demo-password", transport=transport).fetch()
    assert len(snapshot.services) == 3
    assert snapshot.services["tinco:srv:DEMO-INTERNET"].billing.status == BillingStatus.NO_PENDING
    assert snapshot.services["tlk:srv:DEMO-FIJO"].billing.status == BillingStatus.UNAVAILABLE
    password_calls = [c for c in transport.calls if c[1] and "password" in c[1]]
    assert len(password_calls) == 1
    assert password_calls[0][0] == IDP + "password"


def test_existing_session_needs_no_login_and_history_is_optional():
    transport = FakeTransport(
        [Page(HOME, fixture("services.html")), Page(BILLS, fixture("billing.html"))]
    )
    snapshot = MiAntelClient("demo-user", "demo-password", transport=transport).fetch()
    assert snapshot.services["tinco:srv:DEMO-INTERNET"].billing.last_amount is None
    assert len(transport.calls) == 2


def test_history_read_keeps_pending_and_issued_amounts_separate():
    transport = FakeTransport(
        [
            Page(HOME, fixture("services.html")),
            Page(BILLS, fixture("billing.html")),
            Page(HOME + "history", fixture("history.html")),
        ]
    )
    result = MiAntelClient(
        "demo-user", "demo-password", transport=transport, include_history=True
    ).fetch()
    billing = result.services["tinco:srv:DEMO-INTERNET"].billing
    assert billing.last_amount == 99 and billing.pending_amount == 0


def test_billing_server_failure_does_not_erase_balances():
    transport = FakeTransport(
        [Page(HOME, fixture("services.html")), ConnectionError("Upstream failure")]
    )
    result = MiAntelClient("demo-user", "demo-password", transport=transport).fetch()
    assert result.services["acm:srv:DEMO-MOVIL"].balance is not None
    assert not result.billing_available
    assert all(s.billing.status == BillingStatus.UNAVAILABLE for s in result.services.values())


def test_rate_limit_is_not_hidden_as_an_empty_invoice_list():
    transport = FakeTransport([Page(HOME, fixture("services.html")), RateLimited("Rate limit")])
    with pytest.raises(RateLimited):
        MiAntelClient("demo-user", "demo-password", transport=transport).fetch()


def test_wrong_password_is_not_submitted_repeatedly():
    transport = FakeTransport(
        [
            Page(IDP + "username", USER),
            Page(IDP + "password", PASSWORD),
            Page(IDP + "password", PASSWORD),
        ]
    )
    with pytest.raises(AuthenticationError):
        MiAntelClient("demo-user", "demo-password", transport=transport).login()
    assert sum(bool(fields and "password" in fields) for _, fields, _ in transport.calls) == 1


def test_rejected_login_during_refresh_stops_after_one_attempt():
    transport = FakeTransport([
        SessionExpired("Expired"),
        Page(IDP + "username", USER),
        Page(IDP + "password", PASSWORD),
        SessionExpired("Rejected"),
    ])
    with pytest.raises(AuthenticationError):
        MiAntelClient("demo-user", "demo-password", transport=transport).fetch()
    assert not transport.pages
    assert sum(bool(fields and "password" in fields) for _, fields, _ in transport.calls) == 1


def test_login_connection_failure_remains_retryable():
    transport = FakeTransport([SessionExpired("Expired"), ConnectionError("Offline")])
    with pytest.raises(ConnectionError):
        MiAntelClient("demo-user", "demo-password", transport=transport).fetch()
    assert len(transport.calls) == 2


def test_session_expiring_again_after_login_does_not_loop():
    transport = FakeTransport([
        SessionExpired("Expired"), *login_pages(), SessionExpired("Expired again")
    ])
    with pytest.raises(AuthenticationError):
        MiAntelClient("demo-user", "demo-password", transport=transport).fetch()
    assert transport.clears == 1
    assert not transport.pages


def test_sms_step_is_not_automatically_submitted():
    transport = FakeTransport([Page(IDP + "otp", b'<form><input name="otp"></form>')])
    with pytest.raises(AdditionalAuthenticationRequired):
        MiAntelClient("demo-user", "demo-password", transport=transport).login()
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://eidas.tuid.uy/",
        "https://eidas.tuid.uy.evil.invalid/",
        "https://example.invalid/",
        "https://user@example.invalid/",
        "https://eidas.tuid.uy:444/",
        "file:///tmp/demo",
    ],
)
def test_credentials_cannot_follow_an_unexpected_destination(url):
    with pytest.raises(ParseError):
        validate_url(url)


def test_malicious_password_form_is_not_submitted():
    transport = FakeTransport(
        [Page(IDP, PASSWORD.replace(b"/password", b"https://example.invalid/collect"))]
    )
    with pytest.raises(ParseError):
        MiAntelClient("demo-user", "demo-password", transport=transport).login()
    assert len(transport.calls) == 1


def test_transport_exception_does_not_expose_upstream_details():
    transport = HttpTransport()

    class BrokenOpener:
        def open(self, *args, **kwargs):
            raise URLError("DEMO-PRIVATE-CONTENT")

    transport.opener = BrokenOpener()
    with pytest.raises(ConnectionError) as result:
        transport.request(HOME)
    assert "DEMO-PRIVATE-CONTENT" not in str(result.value)


def test_removed_service_is_not_reused_from_old_data():
    first = fixture("services.html")
    empty = b'<html><body id="bodyMiAntel"><h2>Mis servicios 0</h2><div id="servicesTodos"></div></body></html>'
    transport = FakeTransport(
        [
            Page(HOME, first),
            Page(BILLS, fixture("billing.html")),
            Page(HOME, empty),
            Page(BILLS, b"<html/>"),
        ]
    )
    client = MiAntelClient("demo-user", "demo-password", transport=transport)
    assert client.fetch().services
    assert client.fetch().services == {}


def test_tls_setup_runs_in_request_worker_not_home_assistant_event_loop(monkeypatch):
    import asyncio

    events = []

    class Response:
        url = HOME

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return b"<html></html>"

    class Opener:
        def open(self, request, timeout):
            return Response()

    def create_opener(*handlers):
        with pytest.raises(RuntimeError):
            asyncio.get_running_loop()
        events.append("tls-created-in-worker")
        return Opener()

    monkeypatch.setattr("web.client.build_opener", create_opener)

    async def check():
        transport = HttpTransport()
        assert not events
        await asyncio.to_thread(transport.request, HOME)
        await asyncio.to_thread(transport.request, HOME)
        assert events == ["tls-created-in-worker"]

    asyncio.run(check())
