"""Scale connectors: one small interface, several ways to get weight readings into the app.

    Reading(scale_id, location, ingredient, grams, timestamp, source)

Connectors (all return list[Reading]):
  SimulatedScale   deterministic synthetic readings (default in the demo)
  HttpJsonScale    GET a URL that returns readings JSON (smart scale / IoT gateway); timeout + validation
  parse_csv        CSV exported/pushed by a scale gateway (columns below)
  parse_ascii_line one line from a serial/USB scale, e.g. "ST,GS,+  1.234kg"

Serial/USB scales: many speak a simple ASCII protocol over RS-232/USB serial. Read them with `pyserial`
on a small LOCAL gateway PC (pyserial is NOT a requirement of this app), parse each line with
parse_ascii_line(), and POST the readings as the PUSH_PAYLOAD_EXAMPLE JSON to your backend.
Streamlit Community Cloud cannot reach devices on the restaurant network.

Every reading must be reviewed by staff before it changes stock; check_plausibility() flags odd ones.
"""
import csv
import io
import json
import re
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

UNIT_TO_G = {"g": 1.0, "kg": 1000.0, "lb": 453.59237, "oz": 28.349523125}
CSV_COLUMNS = ["scale_id", "location", "ingredient", "value", "unit", "timestamp"]

PUSH_PAYLOAD_EXAMPLE = {
    "gateway_id": "kitchen-gw-1",
    "readings": [
        {"scale_id": "walkin-1", "location": "walk-in fridge", "ingredient": "white_fish",
         "value": 2.85, "unit": "kg", "timestamp": "2026-07-06T09:15:00Z"},
        {"scale_id": "bin-1", "location": "kitchen bin", "ingredient": "mixed / other",
         "value": 420, "unit": "g", "timestamp": "2026-07-06T15:02:10Z"},
    ],
}


@dataclass(frozen=True)
class Reading:
    scale_id: str
    location: str
    ingredient: str
    grams: float
    timestamp: str
    source: str

    def to_dict(self):
        return asdict(self)


def to_grams(value, unit: str) -> float:
    unit = (unit or "").strip().lower()
    if unit not in UNIT_TO_G:
        raise ValueError(f"unknown unit {unit!r} (use g, kg, lb or oz)")
    try:
        return round(float(value) * UNIT_TO_G[unit], 1)
    except (TypeError, ValueError):
        raise ValueError(f"value must be a number, got {value!r}")


def reading_from_dict(d: dict, source: str) -> Reading:
    """Validate one reading in the push/pull JSON format."""
    if not isinstance(d, dict):
        raise ValueError("reading must be an object")
    missing = [k for k in ("scale_id", "location", "ingredient", "value", "unit") if k not in d]
    if missing:
        raise ValueError(f"reading missing fields: {missing}")
    return Reading(str(d["scale_id"]), str(d["location"]), str(d["ingredient"]),
                   to_grams(d["value"], d["unit"]),
                   str(d.get("timestamp") or datetime.now(timezone.utc).isoformat(timespec="seconds")), source)


def parse_payload(payload, source: str) -> list:
    """Accept {"readings": [...]} or a bare list."""
    if isinstance(payload, (str, bytes)):
        payload = json.loads(payload)
    items = payload.get("readings") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError('expected {"readings": [...]} or a list of readings')
    return [reading_from_dict(r, source) for r in items]


class SimulatedScale:
    """Deterministic fake readings around the recorded weights (one deliberately odd for the demo)."""

    def __init__(self, recorded: dict, timestamp: str = "2026-07-06T09:00:00"):
        self.recorded = recorded          # {(ingredient, location): grams}
        self.timestamp = timestamp

    def read(self) -> list:
        out = []
        for i, ((ing, loc), grams) in enumerate(sorted(self.recorded.items())):
            factor = [0.97, 1.02, 0.9, 1.0, 0.95][i % 5]
            if i == 1:
                factor = 0.3               # sudden drop -> should be flagged for review
            out.append(Reading(f"sim-{i + 1}", loc, ing, round(grams * factor, 1), self.timestamp, "simulated"))
        return out

    @staticmethod
    def bin_reading(n: int = 0) -> float:
        """Simulated kitchen-bin scale: deterministic grams for the n-th press."""
        return [420.0, 185.0, 760.0, 310.0][n % 4]


class HttpJsonScale:
    """Pull readings from GET <url> returning PUSH_PAYLOAD_EXAMPLE-style JSON."""

    def __init__(self, url: str, timeout: float = 5.0, fetch=None):
        if not url.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        self.url, self.timeout = url, timeout
        self.fetch = fetch or self._fetch          # injectable for tests

    def _fetch(self, url, timeout):
        with urllib.request.urlopen(url, timeout=timeout) as r:   # noqa: S310 (user-configured URL)
            return r.read(1_000_000)

    def read(self) -> list:
        return parse_payload(self.fetch(self.url, self.timeout), source=f"http:{self.url}")


def parse_csv(file_or_text) -> list:
    """CSV with columns scale_id,location,ingredient,value,unit,timestamp."""
    text = file_or_text if isinstance(file_or_text, str) else file_or_text.read().decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    if rows and set(CSV_COLUMNS[:5]) - set(rows[0]):
        raise ValueError(f"CSV needs columns {CSV_COLUMNS}")
    return [reading_from_dict(r, "csv import") for r in rows]


ASCII_RE = re.compile(r"^\s*(ST|US|OL)\s*,\s*(GS|NT|TR)?\s*,?\s*([+-])?\s*(\d+(?:\.\d+)?)\s*(kg|g|lb|oz)\s*$", re.I)


def parse_ascii_line(line: str) -> dict:
    """Parse a common ASCII weight line, e.g. 'ST,GS,+  1.234kg'.

    ST = stable, US = unstable, OL = overload; GS = gross, NT = net, TR = tare.
    Returns {"grams", "stable", "mode"}; raises ValueError on overload or garbage."""
    m = ASCII_RE.match(line or "")
    if not m:
        raise ValueError(f"unrecognised scale line: {line!r}")
    status, mode, sign, value, unit = m.groups()
    if status.upper() == "OL":
        raise ValueError("scale overload")
    grams = to_grams(value, unit) * (-1 if sign == "-" else 1)
    return {"grams": grams, "stable": status.upper() == "ST", "mode": (mode or "GS").upper()}


def check_plausibility(reading: Reading, previous_grams=None, max_grams: float = 50000, jump_pct: float = 50) -> list:
    """Reasons a reading needs a closer look (empty list = looks plausible)."""
    flags = []
    if reading.grams < 0:
        flags.append("negative weight")
    if reading.grams > max_grams:
        flags.append(f"above max {max_grams:g} g")
    if previous_grams and previous_grams > 0:
        change = 100 * abs(reading.grams - previous_grams) / previous_grams
        if change > jump_pct:
            flags.append(f"sudden change {change:.0f}% vs recorded {previous_grams:g} g")
    return flags
