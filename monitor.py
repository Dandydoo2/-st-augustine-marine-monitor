"""NWS Jacksonville marine monitor. Python 3.12+, standard library only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import smtplib
import ssl
import sys
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

LOCAL = ZoneInfo("America/New_York")
ZONES = {
    "AMZ452": "Fernandina Beach to St. Augustine, out 20 NM",
    "AMZ454": "St. Augustine to Flagler Beach, out 20 NM",
}
API = "https://api.weather.gov"
LIST_URL = API + "/products/types/CWF/locations/JAX"
SOURCE_PAGE = "https://forecast.weather.gov/product.php?site=JAX&issuedby=JAX&product=CWF"
NUM = r"\d+(?:\.\d+)?"
RANGE = rf"({NUM})(?:\s*(?:to|-)\s*({NUM}))?"
VALUE = re.compile(rf"{RANGE}\s*(feet|foot|ft|seconds?|secs?|s)\b", re.I)
WD_COMPONENT = re.compile(rf"{RANGE}\s*(?:feet|foot|ft)\s+at\s+{RANGE}\s*(?:seconds?|secs?|s)\b", re.I)
DAYNAMES = "MONDAY TUESDAY WEDNESDAY THURSDAY FRIDAY SATURDAY SUNDAY".split()
DAY = "(?:" + "|".join(DAYNAMES) + ")"
SINGLE = rf"(?:{DAY}(?: NIGHT)?|REST OF TODAY|REST OF TONIGHT|TODAY|TONIGHT|THIS AFTERNOON|THIS EVENING|OVERNIGHT|THIS MORNING)"
LABEL = rf"{SINGLE}(?: (?:AND|THROUGH) {SINGLE})*"
HEADINGS = re.compile(rf"^\.?({LABEL})(?:\s*\.\.\.|\s*$)", re.M)


def normalized(text):
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\u2028", "\n").replace("\u2029", "\n").replace("\u00a0", " ").replace("–", "-").replace("—", "-").strip().strip("[]").strip()


def http_json(url, user_agent):
    """Retry read-only NWS requests. Never log a secret or a full exception URL."""
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": user_agent, "Accept": "application/ld+json"}), timeout=30) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            if attempt == 2:
                raise RuntimeError("NWS API request failed after three attempts") from None
            time.sleep(2 ** attempt)


def fetch_product(now):
    agent = os.environ.get("NWS_USER_AGENT") or "MarineWindowMonitor/1.0"
    listing = http_json(LIST_URL, agent)
    candidates = [p for p in listing.get("@graph", []) if p.get("issuingOffice") == "KJAX" and p.get("wmoCollectiveId") == "FZUS52" and p.get("productCode") == "CWF"]
    if not candidates:
        raise RuntimeError("NWS returned no FZUS52 KJAX coastal forecasts")
    entry = max(candidates, key=lambda p: datetime.fromisoformat(p["issuanceTime"].replace("Z", "+00:00")))
    product_id = entry.get("id", "")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", product_id):
        raise RuntimeError("Unexpected NWS product identifier")
    product = http_json(API + "/products/" + product_id, agent)
    issued = datetime.fromisoformat(product["issuanceTime"].replace("Z", "+00:00"))
    if issued.tzinfo is None or not -3600 <= (now - issued).total_seconds() <= 24 * 3600:
        raise RuntimeError("NWS forecast is stale (over 24 hours) or has an invalid issue time")
    text = product["productText"]
    if not re.search(r"^FZUS52 KJAX\b", text, re.M) or not re.search(r"^CWFJAX\s*$", text, re.M):
        raise RuntimeError("NWS returned the wrong product")
    return text, issued


def zone_sections(text):
    """Handle combined UGC headers such as AMZ450-452-070700-."""
    sections = {}
    for block in normalized(text).split("$$"):
        header = re.search(r"^(AMZ\d{3}-(?:\s*(?:AMZ)?\d{3}-)*\s*\d{6}-)\s*$", block, re.M)
        if not header:
            continue
        codes = [token.removeprefix("AMZ") for token in re.sub(r"\s+", "", header[1]).split("-") if re.fullmatch(r"(?:AMZ)?\d{3}", token)]
        for code in codes:
            zone = "AMZ" + code
            if zone in ZONES:
                if zone in sections:
                    raise RuntimeError("Duplicate zone section: " + zone)
                sections[zone] = block[header.end():]
    if set(sections) != set(ZONES):
        raise RuntimeError("NWS forecast is missing one of the two requested zones")
    return sections


def bounds(match):
    lo = float(match[1])
    hi = float(match[2] or match[1])
    if hi < lo:
        raise RuntimeError("Reversed numeric range in forecast")
    return lo, hi


def numeric_values(text, unit):
    found = []
    for match in VALUE.finditer(text):
        is_feet = match[3].lower() in {"feet", "foot", "ft"}
        if is_feet == (unit == "feet"):
            found.append(bounds(match))
    return found


def parse_seas(body):
    clauses = re.findall(r"\bSeas\b\s+((?:\.(?=\d)|[^.!?])+)", body, re.I)
    if not clauses:
        return None, None, None
    values, occasional = [], []
    for clause in clauses:
        # Occasional peaks are displayed separately; trigger uses the Seas range.
        clean = re.sub(rf",?\s*occasionally\s+(?:up\s+)?to\s+{RANGE}\s*(?:feet|foot|ft)\b", "", clause, flags=re.I)
        occasional.extend(hi for lo, hi in numeric_values(clause[clause.lower().find("occasionally"):], "feet") if "occasionally" in clause.lower())
        parsed = numeric_values(clean, "feet")
        if not parsed or re.search(r"\b(?:greater|more|over|above|higher|less than|below|under)\b", clean, re.I):
            return None, None, max(occasional, default=None)
        # For '2 feet or less', represent 0..2. 'Around 2' remains around 2.
        if re.search(r"\bor less\b", clean, re.I):
            parsed = [(0, hi) for lo, hi in parsed]
        values.extend(parsed)
    return min(lo for lo, hi in values), max(hi for lo, hi in values), max(occasional, default=None)


def parse_period(body, mode):
    explicit = re.findall(r"\bDominant(?:\s+wave)?\s+period\b\s*(?:is\s+|of\s+|[:=]\s*)?((?:\.(?=\d)|[^.!?])+)", body, re.I)
    if explicit:
        vals = []
        for clause in explicit:
            if re.search(r"\b(?:less than|or less|under|below|around|about)\b", clause, re.I):
                return None, None, "not listed"
            v = numeric_values(clause, "seconds")
            if not v:
                return None, None, "not listed"
            vals.extend(v)
        return min(lo for lo, hi in vals), max(hi for lo, hi in vals), "dominant"
    if mode == "strict":
        return None, None, "not listed"
    detail = re.findall(r"\bWave Detail:\s*((?:\.(?=\d)|[^.!?])+)", body, re.I)
    if not detail:
        return None, None, "not listed"
    selected = []
    for clause in detail:
        # A 'becoming' separates successive sea states. Require all to qualify.
        for phase in re.split(r"\b(?:becoming|then|building to|subsiding to|increasing to|decreasing to)\b", clause, flags=re.I):
            components = []
            for m in WD_COMPONENT.finditer(phase):
                components.append((float(m[2] or m[1]), float(m[3]), float(m[4] or m[3])))
            if not components:
                return None, None, "not listed"
            height = max(c[0] for c in components)
            selected.extend((lo, hi) for h, lo, hi in components if h == height)
    return min(lo for lo, hi in selected), max(hi for lo, hi in selected), "wave detail"


def heading_slots(label, issue_date):
    def one(part):
        night = "NIGHT" in part or part in {"THIS EVENING", "OVERNIGHT"}
        weekday = next((i for i, name in enumerate(DAYNAMES) if part.startswith(name)), None)
        offset = 0 if weekday is None else (weekday - issue_date.weekday()) % 7
        return offset * 2 + int(night)
    slots = []
    for part in label.split(" AND "):
        endpoints = part.split(" THROUGH ")
        if len(endpoints) > 2:
            raise RuntimeError("Unsupported compound THROUGH heading")
        first, last = one(endpoints[0]), one(endpoints[-1])
        if last < first:
            last += 14
        for index in range(first, last + 1):
            slots.append(((issue_date + timedelta(days=index // 2)).isoformat(), "N" if index % 2 else "D"))
    return slots


def parse_zone(text, issued, mode="wave_detail"):
    text = normalized(text)
    headings = list(HEADINGS.finditer(text))
    if not headings:
        raise RuntimeError("No recognizable forecast period headings")
    # An unfamiliar period must produce a visible failure, not attach to another day.
    for line in text.splitlines():
        if re.match(r"^\.[A-Z][A-Z ]+\.\.\.", line) and not HEADINGS.match(line):
            raise RuntimeError("Unrecognized NWS forecast period heading")
    records = []
    for i, heading in enumerate(headings):
        body = text[heading.end():headings[i+1].start() if i+1 < len(headings) else len(text)]
        lo, hi, occ = parse_seas(" ".join(body.split()))
        plo, phi, source = parse_period(" ".join(body.split()), mode)
        for date, slot in heading_slots(heading[1], issued.astimezone(LOCAL).date()):
            records.append({"date": date, "slot": slot, "seas_lo": lo, "seas_hi": hi, "occasional": occ, "period_lo": plo, "period_hi": phi, "source": source})
    # Merge repeated/partial headings conservatively; no favorable cherry-picking.
    merged = {}
    for rec in records:
        key = rec["date"], rec["slot"]
        if key not in merged:
            merged[key] = rec
            continue
        old = merged[key]
        for low, high in [("seas_lo", "seas_hi"), ("period_lo", "period_hi")]:
            if old[low] is None or rec[low] is None:
                old[low] = old[high] = None
            else:
                old[low], old[high] = min(old[low], rec[low]), max(old[high], rec[high])
        peaks = [p for p in (old["occasional"], rec["occasional"]) if p is not None]
        old["occasional"] = max(peaks, default=None)
        if old["period_lo"] is None:
            old["source"] = "not listed"
        elif "wave detail" in {old["source"], rec["source"]}:
            old["source"] = "wave detail"
    return list(merged.values())


def qualifies(record):
    return record["seas_hi"] is not None and record["period_lo"] is not None and record["seas_hi"] <= 2 and record["period_lo"] >= 7


def next_week(records, now):
    start = now.astimezone(LOCAL).date()
    dates = {(start + timedelta(days=i)).isoformat() for i in range(7)}
    return [r for r in records if r["date"] in dates]


def signature(zones, mode):
    matches = sorted((zone, r["date"], r["slot"], r["seas_lo"], r["seas_hi"], r["period_lo"], r["period_hi"], r["source"], r["occasional"]) for zone, records in zones.items() for r in records if qualifies(r))
    if not matches:
        return None
    return hashlib.sha256(json.dumps([mode, matches], separators=(",", ":")).encode()).hexdigest()


def fmt_num(n):
    return f"{n:g}"


def fmt_range(lo, hi):
    if lo == 0 and hi != 0:
        return "<=" + fmt_num(hi)
    return fmt_num(lo) if lo == hi else f"{fmt_num(lo)}-{fmt_num(hi)}"


def compact(record):
    sea = "seas not listed" if record["seas_hi"] is None else fmt_range(record["seas_lo"], record["seas_hi"]) + "ft"
    if record["occasional"] is not None:
        sea += " (occ " + fmt_num(record["occasional"]) + ")"
    period = "period not listed" if record["period_lo"] is None else fmt_range(record["period_lo"], record["period_hi"]) + "s" + ("*" if record["source"] == "wave detail" else "")
    return ("✅" if qualifies(record) else "") + f"{record['slot']} {sea}/{period}"


def format_message(zones, issued, now, test=False):
    rows = [("TEST ONLY - " if test else "") + "NWS JAX: seas <=2ft & period >=7s", "Issued " + issued.astimezone(LOCAL).strftime("%m/%d %I:%M%p %Z")]
    start = now.astimezone(LOCAL).date()
    for zone, records in zones.items():
        rows.append(zone + " " + ZONES[zone])
        for i in range(7):
            date = start + timedelta(days=i)
            periods = sorted([r for r in records if r["date"] == date.isoformat()], key=lambda r:r["slot"])
            summary = "; ".join(compact(r) for r in periods) if periods else "forecast not available"
            rows.append(date.strftime("%a %m/%d") + " " + summary)
    rows.append("D=day N=night; *=tallest Wave Detail component, estimated period. Missing periods do not match.")
    rows.append("7 calendar days including today; absent periods unavailable. Criteria match is not a boating safety assessment. Tap link for full NWS text.")
    message = "\n".join(rows)
    if len(message.encode("utf-8")) > 4096:
        raise RuntimeError("Summary exceeds ntfy's 4096-byte message limit")
    return message


def publish(message, title):
    topic = os.environ.get("NTFY_TOPIC", "")
    if not re.fullmatch(r"[-_A-Za-z0-9]{32,64}", topic):
        raise RuntimeError("Set NTFY_TOPIC to a random 32-64 character topic using letters/numbers/dashes/underscores")
    headers = {"Title": title, "Click": SOURCE_PAGE, "Content-Type": "text/plain; charset=utf-8", "Priority": "3"}
    token = os.environ.get("NTFY_TOKEN", "").strip()
    email = os.environ.get("NTFY_EMAIL", "").strip()
    if email:
        if not token:
            raise RuntimeError("Email alerts require NTFY_TOKEN")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise RuntimeError("Set NTFY_EMAIL to your verified email address")
        headers["Email"] = email
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request("https://ntfy.sh/" + topic, data=message.encode("utf-8"), method="POST", headers=headers)
    # No automatic retry: an uncertain response could otherwise duplicate a push.
    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
            if result.get("event") != "message":
                raise RuntimeError("Unexpected ntfy response")
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        raise RuntimeError("ntfy publish failed; check your phone before manually retrying") from None


def backup_email(message, title):
    """Opt-in SMTP copy, only after the gateway was personally confirmed working."""
    if os.environ.get("GATEWAY_ENABLED", "").lower() != "true":
        return True
    required = ["PHONE_NUMBER", "CARRIER_GATEWAY", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"]
    if any(not os.environ.get(name) for name in required):
        print("Backup email skipped: required secrets missing.")
        return False
    phone = re.sub(r"\D", "", os.environ["PHONE_NUMBER"])
    domain = os.environ["CARRIER_GATEWAY"]
    if not re.fullmatch(r"\d{10}", phone) or not re.fullmatch(r"[a-zA-Z0-9.-]+", domain):
        print("Backup email skipped: invalid phone/domain setting.")
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = os.environ["SMTP_FROM"], phone + "@" + domain, title
    msg.set_content(message)
    try:
        with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "465")), timeout=30, context=ssl.create_default_context()) as smtp:
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
        print("Backup email accepted by SMTP; this does not prove SMS delivery.")
        return True
    except Exception:
        print("Backup email failed; primary ntfy delivery was not affected.")
        return False


def load_state(path):
    if not path.exists():
        return {"version": 1, "active_signature": None}
    state = json.loads(path.read_text())
    if state.get("version") != 1 or "active_signature" not in state:
        raise RuntimeError("Unsupported or corrupt state file")
    return state


def save_state(path, state):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    temp.replace(path)


def run(args):
    mode = os.environ.get("PERIOD_MODE", "wave_detail")
    if mode not in {"strict", "wave_detail"}:
        raise RuntimeError("PERIOD_MODE must be strict or wave_detail")
    now = datetime.now(timezone.utc)
    if args.mode == "test":
        publish("TEST ONLY: Your marine forecast notification connection works. No real forecast match is implied.", "Marine monitor connection test")
        backup_email("TEST ONLY: Marine monitor connection test.", "Marine monitor test")
        print("Test accepted by ntfy. Confirm receipt on your iPhone.")
        return
    if args.mode in {"sample", "sample-alert"}:
        now = issued = datetime(2026, 10, 6, 16, tzinfo=timezone.utc)
        filename = "sample.txt" if args.mode == "sample" else "sample-match.txt"
        # Standalone user sample lacks zone identifiers: apply it to both ONLY in tests.
        text = Path(filename).read_text()
        zones = {z: next_week(parse_zone(text, issued, mode), now) for z in ZONES}
    else:
        text, issued = fetch_product(now)
        zones = {z: next_week(parse_zone(block, issued, mode), now) for z, block in zone_sections(text).items()}
    message = format_message(zones, issued, now, test=args.mode in {"sample", "sample-alert"})
    print(message)
    fingerprint = signature(zones, mode)
    print("Matching periods:", sum(qualifies(r) for records in zones.values() for r in records))
    if args.mode in {"sample", "preview"}:
        print("Preview only: no notification sent, no state changed.")
        return
    if args.mode == "sample-alert":
        publish(message, "TEST ONLY: sample matching forecast")
        backup_email(message, "TEST ONLY: sample matching forecast")
        print("Sample test accepted by ntfy; real alert state unchanged.")
        return
    path = Path("state.json")
    state = load_state(path)
    if fingerprint is None:
        if state["active_signature"] is not None:
            state["active_signature"] = None
            save_state(path, state)
        print("No match; no alert sent.")
    elif fingerprint != state["active_signature"]:
        publish(message, "Marine forecast criteria match")
        state.update(active_signature=fingerprint, last_sent_utc=now.isoformat())
        save_state(path, state)
        backup_ok = backup_email(message, "Marine forecast criteria match")
        print("New/changed match accepted by ntfy.")
        if not backup_ok:
            raise RuntimeError("Optional backup failed; primary alert was sent and state was saved")
    else:
        print("Matching forecast unchanged; duplicate suppressed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["check", "preview", "test", "sample", "sample-alert"], default="check")
    try:
        run(parser.parse_args())
    except Exception as exc:
        # Avoid traceback/URLs revealing a topic, phone number or SMTP credentials.
        safe = str(exc) if isinstance(exc, RuntimeError) else "Unexpected error; inspect code/configuration without printing secrets"
        print("ERROR:", safe, file=sys.stderr)
        sys.exit(1)
