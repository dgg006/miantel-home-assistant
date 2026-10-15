"""Conservative parsing of supported MiAntel web views."""

import re
import unicodedata
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from lxml import etree, html

from .errors import ParseError, SessionExpired
from .models import Billing, BillingStatus, Service

MONTHS = {
    name: i
    for i, name in enumerate(
        (
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "setiembre",
            "octubre",
            "noviembre",
            "diciembre",
        ),
        1,
    )
}
MONTHS["septiembre"] = 9


def normalize(value: str) -> str:
    return " ".join(
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold().split()
    )


def text(node) -> str:
    parts = node.xpath(
        ".//text()[not(ancestor::script or ancestor::style or ancestor::template "
        "or ancestor::noscript)]"
    )
    return " ".join(" ".join(parts).split())


def service_name(card, service_id: str) -> str:
    """Prefer the displayed alias, without repeated numbers or JSF scripts."""
    identifier = service_id.replace(":", "-", 2)
    for prefix in ("alias-", "s-"):
        for node in card.xpath(".//*[@id=$identifier]", identifier=prefix + identifier):
            label = text(node)
            if label:
                return label
    headings = card.xpath(".//h5[not(" + cls("mobile") + ")]")
    if headings and (label := text(headings[0])):
        return label
    raise ParseError("Service heading missing")


def cls(value: str) -> str:
    return f'contains(concat(" ",normalize-space(@class)," ")," {value} ")'


def decode(body: bytes) -> str:
    # Some upstream responses declare charset=null or UTF-8 but send Latin-1.
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError:
        return body.decode("iso-8859-1")


def document(body: bytes):
    try:
        return html.fromstring(decode(body), parser=html.HTMLParser(no_network=True))
    except (etree.ParserError, ValueError):
        raise ParseError("Unsupported HTML response") from None


def number(value: str) -> Decimal:
    value = value.replace("\xa0", "").replace(" ", "")
    if not re.fullmatch(r"-?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?", value):
        raise ParseError("Unsupported displayed number")
    try:
        return Decimal(value.replace(".", "").replace(",", "."))
    except InvalidOperation:
        raise ParseError("Invalid displayed number") from None


def identity(card) -> str:
    for value in card.xpath(".//*[@id]/@id"):
        match = re.fullmatch(r"(?:s|alias)-(acm|tinco|tlk)-srv-(.+)", value)
        if match:
            return f"{match[1]}:srv:{match[2]}"
    raise ParseError("Service identifier missing")


def expiry(label: str, today: date) -> date | None:
    match = re.search(r"vence el (\d{1,2}) de ([a-z]+).*?\((\d+) dias?\)", normalize(label))
    if not match or match[2] not in MONTHS:
        return None
    result = today + timedelta(days=int(match[3]))
    return result if (result.day, result.month) == (int(match[1]), MONTHS[match[2]]) else None


def parse_services(root, today: date) -> dict[str, Service]:
    containers = root.xpath('//*[@id="servicesTodos"]')
    if len(containers) != 1:
        raise ParseError("Service view missing")
    cards = containers[0].xpath(".//*[" + cls("servicioBox") + "]")
    counts = root.xpath('//*[@id="cantServicios"]|//h2')
    expected = None
    for element in counts:
        match = re.search(r"mis servicios\s*(\d+)", normalize(text(element)))
        if match:
            expected = int(match[1])
            break
    # JSF can update the cards before its separate header counter (initially zero).
    if expected and len(cards) != expected:
        raise ParseError("Service view is incomplete")
    if not cards and expected != 0:
        raise ParseError("Empty unrecognized service view")
    result = {}
    for card in cards:
        service_id = identity(card)
        if service_id in result:
            raise ParseError("Duplicate service identifier")
        name = service_name(card, service_id)
        plan_nodes = card.xpath(".//*[" + cls("card-header") + "]//*[" + cls("fs-16") + "]")
        balance_nodes = card.xpath(".//span[" + cls("display-3") + "]")
        data_nodes = card.xpath(".//span[" + cls("value-data") + "]")
        usage = None
        if data_nodes:
            unit = re.search(r"\b([KMGT]?B)\b", text(data_nodes[0].getparent()))
            if unit and unit[1] in ("GB", "MB", "KB", "B"):
                divisor = {
                    "GB": Decimal(1),
                    "MB": Decimal(1024),
                    "KB": Decimal(1024**2),
                    "B": Decimal(1024**3),
                }[unit[1]]
                usage = number(text(data_nodes[0])) / divisor
        allowance = None
        for label in card.xpath(".//*[" + cls("progress-bar__label") + "]"):
            match = re.search(r"incluido\s+([\d.,]+)\s*gb\b", normalize(text(label)))
            if match:
                allowance = number(match[1])
        expires = next(
            (
                expiry(text(p), today)
                for p in card.xpath(".//p")
                if normalize(text(p)).startswith("vence el")
            ),
            None,
        )
        result[service_id] = Service(
            service_id=service_id,
            name=name,
            kind=service_id.split(":")[0],
            plan=text(plan_nodes[0]) if plan_nodes else None,
            balance=number(text(balance_nodes[0])) if balance_nodes else None,
            usage_gib=usage,
            allowance_gib=allowance,
            balance_expiry=expires,
        )
    return result


def money(value: str) -> tuple[Decimal, str]:
    match = re.fullmatch(r"\s*(U\$S|USD|UYU|\$)\s*([\d.,]+)\s*", value)
    if not match:
        raise ParseError("Unsupported invoice currency or amount")
    return number(match[2]), "USD" if match[1] in ("U$S", "USD") else "UYU"


def parse_billing_card(card, today: date) -> Billing:
    value = normalize(text(card))
    if "no se pudo obtener informaci" in value:
        return Billing(status=BillingStatus.UNAVAILABLE)
    if re.search(r"no hay facturas pendientes? de pago", value):
        return Billing(
            status=BillingStatus.NO_PENDING,
            pending_count=0,
            pending_amount=Decimal(0),
            currency="UYU",
            overdue=False,
        )
    # Only interpret tables with explicit, recognized headers. Never sum all
    # amounts on a card (which can include offers, history or installment plans).
    for table in card.xpath(".//table"):
        rows = table.xpath(".//tr")
        if not rows:
            continue
        headers = [normalize(text(c)) for c in rows[0].xpath("./th|./td")]
        due_col = next(
            (i for i, h in enumerate(headers) if h in ("vencimiento", "fecha de vencimiento")), None
        )
        amount_col = next(
            (i for i, h in enumerate(headers) if h in ("monto", "importe", "importe a pagar")), None
        )
        if due_col is None or amount_col is None:
            continue
        amounts, dates, currencies = [], [], set()
        for row in rows[1:]:
            cells = row.xpath("./td")
            if len(cells) <= max(due_col, amount_col):
                raise ParseError("Incomplete pending invoice row")
            try:
                due = (
                    date.fromisoformat(text(cells[due_col]))
                    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text(cells[due_col]))
                    else datetime.strptime(text(cells[due_col]), "%d/%m/%Y").date()
                )
            except ValueError:
                raise ParseError("Unsupported invoice date") from None
            amount, currency = money(text(cells[amount_col]))
            amounts.append(amount)
            currencies.add(currency)
            dates.append(due)
        if dates and len(currencies) == 1:
            return Billing(
                status=BillingStatus.PENDING,
                pending_count=len(dates),
                pending_amount=sum(amounts, Decimal(0)),
                currency=currencies.pop(),
                next_due=min(dates),
                overdue=any(d < today for d in dates),
            )
        if dates:
            return Billing(
                status=BillingStatus.PENDING,
                pending_count=len(dates),
                next_due=min(dates),
                overdue=any(d < today for d in dates),
            )
    if re.search(r"facturas? pendientes?|facturas? vencidas?", value):
        return Billing(status=BillingStatus.PENDING)
    return Billing(status=BillingStatus.UNKNOWN)


def billing_cards(root):
    return root.xpath("//*[" + cls("card-base--dashboard") + "]")


def parse_history(root, billing: Billing) -> Billing:
    invoices = []
    for table in root.xpath("//table"):
        rows = table.xpath(".//tr")
        if not rows:
            continue
        headers = [normalize(text(c)) for c in rows[0].xpath("./th|./td")]
        if "fecha de facturacion" not in headers or "monto" not in headers:
            continue
        date_index, amount_index = headers.index("fecha de facturacion"), headers.index("monto")
        for row in rows[1:]:
            cells = row.xpath("./td")
            if len(cells) <= max(date_index, amount_index):
                continue
            try:
                issued = datetime.strptime(text(cells[date_index]), "%d/%m/%Y").date()
                amount, currency = money(text(cells[amount_index]))
            except (ValueError, ParseError):
                raise ParseError("Unsupported invoice history row") from None
            invoices.append((issued, amount, currency))
    if not invoices:
        return billing
    issued, amount, currency = max(invoices, key=lambda item: item[0])
    return replace(
        billing,
        last_amount=amount,
        last_currency=currency,
        last_date=issued,
        history_available=True,
    )


def bootstrap(root):
    scripts = "\n".join(s.text or "" for s in root.xpath("//script[not(@src)]"))
    for match in re.finditer(
        r"command_[A-Za-z0-9_]+\s*=\s*function\(\)\s*\{return PrimeFaces.ab\(\{([^}]+)\}", scripts
    ):
        config = dict(re.findall(r'\b([sfu]):"([^"]+)"', match[1]))
        if "pnlAll" in config.get("u", "").split() and {"s", "f", "u"} <= config.keys():
            form = root.get_element_by_id(config["f"], None)
            if form is None:
                raise ParseError("Home form missing")
            fields = hidden_fields(form)
            fields.update(
                {
                    "javax.faces.partial.ajax": "true",
                    "javax.faces.source": config["s"],
                    "javax.faces.partial.execute": config["s"],
                    "javax.faces.partial.render": config["u"],
                    config["s"]: config["s"],
                }
            )
            return fields
    return None


def partial_document(body: bytes):
    encoding = "utf-8"
    try:
        body.decode(encoding)
    except UnicodeDecodeError:
        encoding = "iso-8859-1"
    try:
        root = etree.fromstring(
            body, parser=etree.XMLParser(encoding=encoding, resolve_entities=False, no_network=True)
        )
    except etree.XMLSyntaxError:
        raise ParseError("Unsupported partial response") from None
    if root.xpath("//redirect|//error"):
        raise SessionExpired("The web view expired")
    updates = root.xpath('//update[@id="pnlAll"]/text()')
    if not updates:
        raise ParseError("Home update missing")
    return document(updates[0].encode("utf-8"))


def hidden_fields(form) -> dict[str, str]:
    return {
        x.get("name"): x.get("value", "") for x in form.xpath('.//input[@type="hidden" and @name]')
    }


def link_submission(root, link):
    onclick = re.sub(r"\\+(['\"])", r"\1", link.get("onclick", ""))
    form_match = re.search(r"getElementById\('([^']+)'\)", onclick)
    command = re.search(r"\{'([^']+)':'[^']+'\}", onclick)
    if not form_match or not command:
        raise ParseError("Unsupported read-only link")
    form = root.get_element_by_id(form_match[1], None)
    if form is None:
        raise ParseError("Read-only form missing")
    fields = hidden_fields(form)
    fields[command[1]] = command[1]
    return form.get("action", ""), fields
