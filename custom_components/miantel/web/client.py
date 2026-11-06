"""Read-only MiAntel web session, suitable for running in a worker thread."""

import threading
from dataclasses import dataclass, replace
from datetime import datetime
from http.cookiejar import CookieJar
from time import monotonic
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

from . import details, parser
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
DESTINATIONS = HOME + "app/destinos-gratis-y-amigos/destinos.jsf"
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
        # Loading system TLS certificates can read disk. Defer it to request(),
        # which Home Assistant calls in its executor, rather than coordinator setup.
        self.opener = None

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
            if self.opener is None:
                self.opener = build_opener(
                    ProxyHandler({}), RestrictedRedirect(), HTTPCookieProcessor(self.cookies)
                )
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
        self, username: str, password: str, *, include_history: bool = False, transport=None,
        include_destinations: bool = False, destination_services=None,
        include_details: bool = False,
    ):
        self._username = username.strip()
        self._password = password
        self.include_history = include_history
        self.include_destinations = include_destinations
        self.destination_services = set(destination_services) if destination_services else None
        self.include_details = include_details
        self._speed_cache = {}
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

    def _services_page(self):
        root = self._read_page(HOME)
        if not root.xpath('//*[@id="servicesTodos"]'):
            fields = parser.bootstrap(root)
            if fields is None:
                raise ParseError("Unsupported service loading view")
            root = self._read_page(HOME, fields, ajax=True)
        return root

    def _fetch_once(self) -> Snapshot:
        now = datetime.now(LOCAL_ZONE)
        root = self._services_page()
        services = parser.parse_services(root, now.date())
        if self.include_details:
            self._read_consumption(services, root, now.date())
        detail_ids = [
            key for key in parser.prepaid_detail_links(root)
            if not self.include_details and key in services and services[key].kind == "acm"
            and services[key].balance is not None and services[key].balance_expiry is None
        ]
        for index, key in enumerate(detail_ids):
            try:
                # Navigation changes the JSF view; obtain fresh commands for each mobile.
                if index:
                    root = self._services_page()
                link = parser.prepaid_detail_links(root).get(key)
                if link is None:
                    continue
                action, fields = parser.link_submission(root, link)
                detail = self._read_page(urljoin(HOME, action), fields)
                value = parser.parse_prepaid_expiry(detail, now.date(), services[key].name)
                services[key] = replace(services[key], balance_expiry=value)
            except RateLimited:
                raise
            except (ParseError, ConnectionError):
                pass  # Preserve independently valid balances and other services.
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
        if self.include_destinations:
            self._read_destinations(services)
        if self.include_details:
            self._read_extra_views(services)
        return Snapshot(services=services, updated_at=now, billing_available=billing_available)

    def _detail_selected(self, key):
        return self.destination_services is None or key in self.destination_services

    def _navigate_service(self, key, labels, root=None):
        if root is None:
            root = self._services_page()
        cards = [card for card in root.xpath('//*[@id="servicesTodos"]//*['
                                            + parser.cls("servicioBox") + "]")
                 if parser.identity(card) == key]
        if len(cards) != 1:
            raise ParseError("Service navigation missing")
        for label in labels:
            links = [a for a in cards[0].xpath(".//a")
                     if parser.normalize(parser.text(a)) == label]
            if links:
                action, fields = parser.link_submission(root, links[0])
                return self._read_page(urljoin(HOME, action), fields)
        raise ParseError("Read-only service navigation missing")

    def _read_consumption(self, services, root, today):
        ids = [key for key, s in services.items()
               if s.kind in ("acm", "tinco") and self._detail_selected(key)]
        for index, key in enumerate(ids):
            try:
                service = services[key]
                view = self._navigate_service(
                    key, ("ver detalle del consumo", "detalle de consumo"),
                    root if not index else None,
                )
                metrics, recharges = details.consumption(
                    view, service.name, today, mobile=service.kind == "acm"
                )
                expiry = service.balance_expiry
                if recharges:
                    expiry = min(r.expires for r in recharges)
                services[key] = replace(service, metrics=metrics, recharges=recharges,
                                        balance_expiry=expiry)
            except RateLimited:
                raise
            except (ConnectionError, ParseError):
                pass

    def _read_extra_views(self, services):
        for key, service in list(services.items()):
            if not self._detail_selected(key):
                continue
            try:
                if service.kind == "acm":
                    view = self._navigate_service(key, ("roaming",))
                    metrics = {"roaming_enabled": details.roaming(view, service.name)}
                elif service.kind == "tinco":
                    cached = self._speed_cache.get(key)
                    if cached and cached[1] == service.plan and monotonic() - cached[0] < 86400:
                        metrics = cached[2]
                    else:
                        # Open the initial plan overview only. No offer is selected or submitted.
                        view = self._navigate_service(key, ("cambiar plan",))
                        metrics = details.plan_speed(view)
                        self._speed_cache[key] = monotonic(), service.plan, metrics
                else:
                    continue
                services[key] = replace(service, metrics={**service.metrics, **metrics})
            except RateLimited:
                raise
            except (ConnectionError, ParseError):
                pass

    def _read_destinations(self, services):
        """Read only the list view; never submit destination management forms."""
        try:
            root = self._read_page(DESTINATIONS)
            ids = [key for key in parser.destination_links(root)
                   if key in services and services[key].kind == "acm"
                   and (self.destination_services is None or key in self.destination_services)]
        except RateLimited:
            raise
        except (ConnectionError, ParseError):
            return
        for index, key in enumerate(ids):
            try:
                if index:
                    root = self._read_page(DESTINATIONS)
                link = parser.destination_links(root).get(key)
                if link is None:
                    continue
                action, fields = parser.link_submission(root, link)
                # Whitelist the navigation command and hidden JSF state only.
                detail = self._read_page(urljoin(DESTINATIONS, action), fields)
                groups = parser.parse_destinations(detail, services[key].name)
                services[key] = replace(services[key], destinations=groups)
            except RateLimited:
                raise
            except (ConnectionError, ParseError):
                pass

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
            self._speed_cache.clear()
