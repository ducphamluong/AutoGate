"""Country name / code normalization to ISO 3166-1 alpha-2."""

from __future__ import annotations

# Common English names + variants used by free VPN list sites.
_NAME_TO_ISO2: dict[str, str] = {
    "afghanistan": "AF",
    "albania": "AL",
    "algeria": "DZ",
    "argentina": "AR",
    "armenia": "AM",
    "australia": "AU",
    "austria": "AT",
    "azerbaijan": "AZ",
    "bahrain": "BH",
    "bangladesh": "BD",
    "belarus": "BY",
    "belgium": "BE",
    "bolivia": "BO",
    "bosnia and herzegovina": "BA",
    "brazil": "BR",
    "bulgaria": "BG",
    "cambodia": "KH",
    "canada": "CA",
    "chile": "CL",
    "china": "CN",
    "colombia": "CO",
    "costa rica": "CR",
    "croatia": "HR",
    "cyprus": "CY",
    "czech republic": "CZ",
    "czechia": "CZ",
    "denmark": "DK",
    "ecuador": "EC",
    "egypt": "EG",
    "estonia": "EE",
    "finland": "FI",
    "france": "FR",
    "georgia": "GE",
    "germany": "DE",
    "greece": "GR",
    "hong kong": "HK",
    "hungary": "HU",
    "iceland": "IS",
    "india": "IN",
    "indonesia": "ID",
    "iran": "IR",
    "iraq": "IQ",
    "ireland": "IE",
    "israel": "IL",
    "italy": "IT",
    "japan": "JP",
    "jordan": "JO",
    "kazakhstan": "KZ",
    "kenya": "KE",
    "korea": "KR",
    "south korea": "KR",
    "republic of korea": "KR",
    "kuwait": "KW",
    "latvia": "LV",
    "lithuania": "LT",
    "luxembourg": "LU",
    "malaysia": "MY",
    "mexico": "MX",
    "moldova": "MD",
    "mongolia": "MN",
    "morocco": "MA",
    "myanmar": "MM",
    "nepal": "NP",
    "netherlands": "NL",
    "the netherlands": "NL",
    "new zealand": "NZ",
    "nigeria": "NG",
    "north macedonia": "MK",
    "norway": "NO",
    "pakistan": "PK",
    "panama": "PA",
    "peru": "PE",
    "philippines": "PH",
    "poland": "PL",
    "portugal": "PT",
    "qatar": "QA",
    "romania": "RO",
    "russia": "RU",
    "russian federation": "RU",
    "saudi arabia": "SA",
    "serbia": "RS",
    "singapore": "SG",
    "slovakia": "SK",
    "slovenia": "SI",
    "south africa": "ZA",
    "spain": "ES",
    "sri lanka": "LK",
    "sweden": "SE",
    "switzerland": "CH",
    "taiwan": "TW",
    "thailand": "TH",
    "turkey": "TR",
    "türkiye": "TR",
    "ukraine": "UA",
    "united arab emirates": "AE",
    "uae": "AE",
    "united kingdom": "GB",
    "uk": "GB",
    "great britain": "GB",
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
    "us": "US",
    "uruguay": "UY",
    "uzbekistan": "UZ",
    "venezuela": "VE",
    "vietnam": "VN",
    "viet nam": "VN",
}


def normalize_country(value: str | None) -> str:
    """Return uppercase ISO2 or empty string if unknown."""
    if not value:
        return ""
    raw = value.strip()
    if not raw:
        return ""

    # Already ISO2 / ISO3-ish codes
    upper = raw.upper().replace(" ", "")
    if len(upper) == 2 and upper.isalpha():
        # UK commonly used for GB
        if upper == "UK":
            return "GB"
        return upper

    key = raw.lower().strip()
    key = key.replace("_", " ").replace("-", " ")
    key = " ".join(key.split())
    if key in _NAME_TO_ISO2:
        return _NAME_TO_ISO2[key]

    # Strip parenthetical "Japan (JP)" / trailing codes
    if "(" in key and ")" in key:
        inside = key[key.find("(") + 1 : key.find(")")]
        if len(inside) == 2 and inside.isalpha():
            return inside.upper()
        outer = key[: key.find("(")].strip()
        if outer in _NAME_TO_ISO2:
            return _NAME_TO_ISO2[outer]

    return ""


def parse_country_filter(raw: str | None) -> set[str]:
    """Parse COUNTRY_FILTER env into ISO2 set.

    Empty set = no filter (all countries).
    Sentinels treated as all: empty, ``all``, ``*``, ``any``.
    """
    if not raw:
        return set()
    cleaned = raw.strip()
    if not cleaned:
        return set()
    if cleaned.lower() in {"all", "*", "any"}:
        return set()
    result: set[str] = set()
    for part in cleaned.split(","):
        token = part.strip()
        if not token or token.lower() in {"all", "*", "any"}:
            continue
        code = normalize_country(token)
        if code:
            result.add(code)
    return result
