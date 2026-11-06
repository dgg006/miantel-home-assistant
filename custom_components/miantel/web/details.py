"""Read-only consumption, roaming and current-plan views."""

import re
from datetime import date, timedelta

from . import parser
from .errors import ParseError
from .models import Recharge


def ensure_service_view(root, name, title):
    headings = [parser.normalize(parser.text(h)) for h in root.xpath("//h2")]
    name = parser.normalize(name)
    if (
        not headings
        or not (
            headings[0] == name
            or (
                headings[0].startswith(name + " ")
                and re.fullmatch(r"\d{8,9}", headings[0][len(name) + 1 :])
            )
        )
        or title not in headings
    ):
        raise ParseError("Unexpected service detail view")


def cycle(root, today):
    labels = [parser.normalize(parser.text(p)) for p in root.xpath("//p|//label|//span")]
    periods = {
        m.groups()
        for t in labels
        if (m := re.fullmatch(r"ciclo actual:\s*(\d{1,2}) de ([a-z]+) al (\d{1,2}) de ([a-z]+)", t))
    }
    remaining = {
        int(m[1]) for t in labels if (m := re.fullmatch(r"quedan? (\d+) dias? para renovar", t))
    }
    if not periods and not remaining:
        return {}
    if len(periods) != 1 or len(remaining) != 1:
        raise ParseError("Ambiguous consumption cycle")
    start_day, start_month, end_day, end_month = next(iter(periods))
    if start_month not in parser.MONTHS or end_month not in parser.MONTHS:
        raise ParseError("Unknown cycle month")
    start_md = parser.MONTHS[start_month], int(start_day)
    end_md = parser.MONTHS[end_month], int(end_day)
    candidates = []
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            start = date(year, *start_md)
            end = date(year + (end_md < start_md), *end_md)
        except ValueError:
            continue
        if start <= today <= end:
            candidates.append((start, end))
    if len(candidates) != 1:
        raise ParseError("Invalid consumption cycle")
    start, end = candidates[0]
    days = next(iter(remaining))
    renewal = end + timedelta(days=1)
    if renewal != today + timedelta(days=days):
        raise ParseError("Inconsistent cycle renewal")
    return {"cycle_start": start, "cycle_end": end, "renewal_date": renewal, "renewal_days": days}


def recharges(root, today):
    cards = root.xpath("//*[" + parser.cls("mini-card-recarga") + "]")
    result = []
    for card in cards:
        headers = card.xpath(".//*[" + parser.cls("card-header") + "]")
        if len(headers) != 1:
            raise ParseError("Unknown recharge header")
        labels = headers[0].xpath(".//p")
        if not labels or parser.normalize(parser.text(labels[0])) != "recarga saldo":
            continue
        expiry_labels = [
            parser.text(p)
            for p in labels[1:]
            if parser.normalize(parser.text(p)).startswith("vence el")
        ]
        amounts = card.xpath(".//*[" + parser.cls("card-body") + "]//span")
        signs = card.xpath(".//*[" + parser.cls("card-body") + "]//small")
        if len(expiry_labels) != 1 or len(amounts) != 1 or len(signs) != 1:
            raise ParseError("Incomplete recharge detail")
        if parser.text(signs[0]) != "$":
            raise ParseError("Unknown recharge currency")
        expiry = parser.expiry(expiry_labels[0], today)
        amount = parser.number(parser.text(amounts[0]))
        if expiry is None or amount < 0:
            raise ParseError("Invalid recharge balance or date")
        result.append(Recharge(amount, expiry))
    if result:
        return tuple(sorted(result, key=lambda x: x.expires))
    # No cards on a monthly plan does not mean zero prepaid recharges.
    labels = [parser.normalize(parser.text(p)) for p in root.xpath("//p")]
    if "no tenes recargas activas" in labels:
        return ()
    return None


def spending(root):
    result = {}
    keys = {"llamadas": "calls", "datos": "data", "sms": "sms", "otros": "other"}
    seen = set()
    for block in root.xpath("//*[" + parser.cls("CombouseMiPlanMobile") + "]"):
        columns = block.xpath("./div")
        if not columns:
            raise ParseError("Empty consumption breakdown")
        labels = columns[0].xpath("./p")
        if not labels:
            raise ParseError("Consumption category missing")
        category = parser.normalize(parser.text(labels[0]))
        if category not in keys or category in seen:
            raise ParseError("Unknown or duplicate consumption category")
        seen.add(category)
        amounts = columns[0].xpath(".//strong")
        if len(amounts) != 1:
            raise ParseError("Consumption amount missing")
        amount, currency = parser.money(parser.text(amounts[0]))
        if currency != "UYU" or amount < 0:
            raise ParseError("Invalid consumption amount")
        key = keys[category]
        result[key + "_spent"] = amount
        if category == "otros":
            continue
        if len(columns) != 2:
            raise ParseError("Consumption equivalent missing")
        values = columns[1].xpath(".//strong")
        if len(values) != 1:
            raise ParseError("Unknown consumption equivalent")
        match = re.fullmatch(r"([\d.,]+)\s*(min\.|MB|GB|SMS)", parser.text(values[0]))
        if not match:
            raise ParseError("Unknown consumption unit")
        value = parser.number(match[1])
        if value < 0:
            raise ParseError("Invalid consumption quantity")
        unit = match[2]
        if category == "llamadas" and unit == "min.":
            result["calls_used_minutes"] = value
        elif category == "datos" and unit in ("MB", "GB"):
            result["mobile_data_used_gib"] = value / (1024 if unit == "MB" else 1)
        elif category == "sms" and unit == "SMS" and value == int(value):
            result["sms_used_count"] = int(value)
        else:
            raise ParseError("Mismatched consumption equivalent")
    return result


def consumption(root, service_name, today, *, mobile):
    ensure_service_view(root, service_name, "detalle de mi consumo")
    metrics = {}
    for parse in (lambda: cycle(root, today), lambda: spending(root) if mobile else {}):
        try:
            metrics.update(parse())
        except ParseError:
            pass  # One unsupported section must not erase independent readings.
    balances = None
    if mobile:
        try:
            balances = recharges(root, today)
        except ParseError:
            pass
    return metrics, balances


def roaming(root, service_name):
    ensure_service_view(root, service_name, "roaming internacional")
    inputs = root.xpath('//input[@type="checkbox" and @name="switchTest"]')
    if len(inputs) != 1:
        raise ParseError("Roaming status missing")
    return inputs[0].get("checked") is not None


def plan_speed(root):
    if not any(parser.normalize(parser.text(h)) == "mejorar plan" for h in root.xpath("//h2")):
        raise ParseError("Current plan view missing")
    markers = [
        x
        for x in root.xpath("//*")
        if not len(x) and parser.normalize(parser.text(x)) == "tu plan actual"
    ]
    if len(markers) != 1:
        raise ParseError("Current plan is ambiguous")
    cards = [x for x in markers[0].iterancestors() if "card-planes" in x.get("class", "").split()]
    if not cards:
        raise ParseError("Current plan card missing")
    matches = re.findall(r"([\d.,]+)\s*/\s*([\d.,]+)\s*Mbps\b", parser.text(cards[0]))
    if len(matches) != 1:
        raise ParseError("Current plan speed missing")
    down, up = (parser.number(x) for x in matches[0])
    if down <= 0 or up <= 0:
        raise ParseError("Invalid contracted speed")
    return {"download_mbps": down, "upload_mbps": up}
