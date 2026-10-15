"""Read-only MiAntel web session, suitable for running in a worker thread."""

import threading
from dataclasses import dataclass, replace
from datetime import datetime
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import (
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)
from zoneinfo import ZoneInfo

from . import parser
from .errors import (
    AdditionalAuthenticationRequired,
    AuthenticationError,
    ConnectionError,
    ParseError,
    RateLimited,
    SessionExpired,
)
from .models import Billing, BillingStatus, Snapshot

HOME = "https://aplicaciones.antel.com.uy/miAntel/"
BILLS = HOME + "app/facturacion/facturas.jsf"
ALLOWED_HOSTS = {"aplicaciones.antel.com.uy", "eidas.tuid.uy"}
MAX_BODY_BYTES = 8 * 1024 * 1024
LOCAL_ZONE = ZoneInfo("America/Montevideo")


def validate_url(url: str) -> None:
    target = urlsplit(url)
    if (
        target.scheme != "https"
        or target.hostname not in ALLOWED_HOSTS
        or target.username
        or target.password
        or target.port not in (None, 443)
    ):
        raise ParseError("Unexpected website destination")


@dataclass(frozen=True, repr=False)
class Page:
    url: str
    body: bytes


class RestrictedRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HttpTransport:
    """One independent in-memory cookie jar per configured account."""

    def __init__(self, timeout: int = 60):
        self.timeout = timeout
        self.cookies = CookieJar()
        self.opener = build_opener(
            ProxyHandler({}), RestrictedRedirect(), HTTPCookieProcessor(self.cookies)
        )

    def clear(self):
        self.cookies.clear()

    def request(self, url: str, fields=None, *, ajax: bool = False) -> Page:
        validate_url(url)
        headers = {"User-Agent": "MiAntel-HomeAssistant/0.1", "Accept": "text/html,application/xml"}
        data = None
        if fields is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = urlencode(fields).encode()
        if ajax:
            headers.update({"Faces-Request": "partial/ajax", "X-Requested-With": "XMLHttpRequest"})
        try:
            with self.opener.open(
                Request(url, data=data, headers=headers), timeout=self.timeout
            ) as response:
                validate_url(response.url)
                body = response.read(MAX_BODY_BYTES + 1)
                if len(body) > MAX_BODY_BYTES:
                    raise ParseError("Website response too large")
                return Page(response.url, body)
        except HTTPError as error:
            status = error.code
            error.close()
            if status == 429:
                raise RateLimited("Website request limit reached") from None
            if status in (401, 403):
                raise SessionExpired("Web authentication required") from None
            raise ConnectionError("Website returned an HTTP error") from None
        except (URLError, TimeoutError, OSError):
            raise ConnectionError("Unable to reach MiAntel") from None


class MiAntelClient:
    """Serialized, read-only queries; no credentials or HTML are logged."""

    def __init__(
        self, username: str, password: str, *, include_history: bool = False, transport=None
    ):
        self._username = username.strip()
        self._password = password
        self.include_history = include_history
        self._transport = transport or HttpTransport()
        self._lock = threading.RLock()

    @staticmethod
    def _authenticated(page: Page) -> bool:
        if urlsplit(page.url).hostname != "aplicaciones.antel.com.uy":
            return False
        root = parser.document(page.body)
        return bool(
            root.xpath('//*[@id="bodyMiAntel"]')
            and root.xpath(
                '//*[@id="pnlAll"]|//*[@id="servicesTodos"]|//*[@id="usuarioBienvenido"]'
            )
        )

    def _request(self, url: str, fields=None, *, ajax=False) -> Page:
        validate_url(url)
        page = self._transport.request(url, fields, ajax=ajax)
        validate_url(page.url)
        return page

    def _submit_auth(self, page, form, fields):
        target = urljoin(page.url, form.get("action", ""))
        validate_url(target)
        if urlsplit(target).hostname != "eidas.tuid.uy":
            raise ParseError("Unexpected authentication form destination")
        return self._request(target, fields)

    def login(self) -> None:
        with self._lock:
            self._transport.clear()
            page = self._request(HOME)
            username_sent = password_sent = False
            for _ in range(16):
                if self._authenticated(page):
                    return
                root = parser.document(page.body)
                selector = root.xpath('//form[@id="flowSelectorForm"]')
                if selector:
                    links = [
                        a
                        for a in selector[0].xpath(".//a")
                        if "usuario y contrase" in parser.normalize(parser.text(a))
                    ]
                    if len(links) != 1:
                        raise AdditionalAuthenticationRequired(
                            "Unsupported TuID identification method"
                        )
                    action, fields = parser.link_submission(root, links[0])
                    target = urljoin(page.url, action)
                    if urlsplit(target).hostname != "eidas.tuid.uy":
                        raise ParseError("Unexpected TuID destination")
                    page = self._request(target, fields)
                    continue
                selected = None
                for form in root.xpath("//form"):
                    hidden = parser.hidden_fields(form)
                    if set(hidden) in ({"request", "x_correlation_id"}, {"response"}):
                        selected, fields = form, hidden
                        break
                    password_inputs = form.xpath('.//input[@type="password" and @name]')
                    user_inputs = form.xpath('.//input[@name="userIdentifier"]')
                    if password_inputs:
                        if password_sent:
                            raise AuthenticationError("TuID did not accept the login")
                        if len(password_inputs) != 1:
                            raise AdditionalAuthenticationRequired("Unsupported TuID login form")
                        fields = hidden
                        fields[password_inputs[0].get("name")] = self._password
                        password_sent = True
                    elif user_inputs:
                        if username_sent:
                            raise AuthenticationError("TuID did not accept the account")
                        fields = hidden
                        fields["userIdentifier"] = self._username
                        username_sent = True
                    else:
                        continue
                    buttons = form.xpath('.//input[@type="submit" and @name and @name!="error"]')
                    if len(buttons) != 1:
                        raise AdditionalAuthenticationRequired("Unsupported TuID submission step")
                    fields[buttons[0].get("name")] = buttons[0].get("value", "")
                    selected = form
                    break
                if selected is None:
                    raise AdditionalAuthenticationRequired(
                        "TuID requires an additional identification step"
                    )
                page = self._submit_auth(page, selected, fields)
            raise AdditionalAuthenticationRequired("TuID login did not complete")

    def _read_page(self, url, fields=None, *, ajax=False):
        page = self._request(url, fields, ajax=ajax)
        if urlsplit(page.url).hostname != "aplicaciones.antel.com.uy":
            raise SessionExpired("Web session expired")
        if ajax:
            return parser.partial_document(page.body)
        root = parser.document(page.body)
        if root.xpath('//input[@name="userIdentifier" or @type="password"]'):
            raise SessionExpired("Web session expired")
        return root

    def _fetch_once(self) -> Snapshot:
        now = datetime.now(LOCAL_ZONE)
        root = self._read_page(HOME)
        if not root.xpath('//*[@id="servicesTodos"]'):
            fields = parser.bootstrap(root)
            if fields is None:
                raise ParseError("Unsupported service loading view")
            root = self._read_page(HOME, fields, ajax=True)
        services = parser.parse_services(root, now.date())
        billing_available = True
        try:
            bills_root = self._read_page(BILLS)
            cards = parser.billing_cards(bills_root)
            if services and not cards:
                # A prepaid-only account need not have a billing view.
                if any(s.kind in ("tinco", "tlk") for s in services.values()):
                    raise ParseError("Billing view missing")
            for card in cards:
                service_id = parser.identity(card)
                if service_id not in services:
                    continue
                try:
                    billing = parser.parse_billing_card(card, now.date())
                except ParseError:
                    billing = Billing(status=BillingStatus.UNKNOWN)
                if self.include_history and billing.status != BillingStatus.UNAVAILABLE:
                    links = [
                        a
                        for a in card.xpath(".//a")
                        if "historico de facturas" in parser.normalize(parser.text(a))
                    ]
                    if len(links) == 1:
                        try:
                            action, fields = parser.link_submission(bills_root, links[0])
                            history = self._read_page(urljoin(BILLS, action), fields)
                            billing = parser.parse_history(history, billing)
                        except RateLimited:
                            raise
                        except (ParseError, ConnectionError):
                            pass  # Keep independently valid pending-invoice information.
                services[service_id] = replace(services[service_id], billing=billing)
            seen = {parser.identity(card) for card in cards}
            for key, service in services.items():
                if service.kind in ("tinco", "tlk") and key not in seen:
                    services[key] = replace(
                        service, billing=Billing(status=BillingStatus.UNAVAILABLE)
                    )
        except RateLimited:
            raise
        except (ConnectionError, ParseError):
            billing_available = False
            services = {
                key: replace(service, billing=Billing(status=BillingStatus.UNAVAILABLE))
                for key, service in services.items()
            }
        return Snapshot(services=services, updated_at=now, billing_available=billing_available)

    def fetch(self) -> Snapshot:
        with self._lock:
            try:
                return self._fetch_once()
            except SessionExpired:
                try:
                    self.login()
                    return self._fetch_once()
                except SessionExpired:
                    raise AuthenticationError("MiAntel could not restore the session") from None

    def close(self):
        with self._lock:
            self._transport.clear()
