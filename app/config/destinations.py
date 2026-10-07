"""Destination, home-currency and period configuration.

Everything the ranking engine needs to know about *which* places to rank lives
here. Add, remove or disable entries without touching the analytics code.

`iso_numeric` (ISO 3166-1 numeric) links a destination to its shape on the
World Map; the map geometry uses these ids, so countries are never matched by
name. `map_point` (longitude, latitude) is set only for places too small to
show as a shape at world scale; they are drawn as a marker instead.

`cpi_code` / `cpi_index` identify the consumer-price series in the IMF CPI
dataset (IMF.STA:CPI). `cpi_code` is normally the ISO 3166 alpha-3 code; the
euro area aggregate is "G163" with the HICP index.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Destination:
    id: str  # URL slug, e.g. /country/japan
    country: str
    display_name: str
    iso2: str
    currency_code: str
    currency_name: str
    flag: str
    region: str
    cpi_code: str
    iso_numeric: str
    cpi_index: str = "CPI"
    enabled: bool = True
    map_point: tuple[float, float] | None = None


@dataclass(frozen=True)
class HomeCurrency:
    code: str
    currency_name: str
    country: str
    display_name: str
    flag: str
    cpi_code: str
    cpi_index: str = "CPI"


@dataclass(frozen=True)
class Period:
    key: str
    label: str
    years: int


DESTINATIONS: tuple[Destination, ...] = (
    # Asia
    Destination("japan", "Japan", "Japan", "JP", "JPY", "Japanese Yen", "🇯🇵", "Asia", "JPN", "392"),
    Destination("thailand", "Thailand", "Thailand", "TH", "THB", "Thai Baht", "🇹🇭", "Asia", "THA", "764"),
    Destination("indonesia", "Indonesia", "Indonesia (Bali)", "ID", "IDR", "Indonesian Rupiah", "🇮🇩", "Asia", "IDN", "360"),
    Destination("vietnam", "Vietnam", "Vietnam", "VN", "VND", "Vietnamese Dong", "🇻🇳", "Asia", "VNM", "704"),
    Destination("south-korea", "South Korea", "South Korea", "KR", "KRW", "South Korean Won", "🇰🇷", "Asia", "KOR", "410"),
    Destination("singapore", "Singapore", "Singapore", "SG", "SGD", "Singapore Dollar", "🇸🇬", "Asia", "SGP", "702", map_point=(103.82, 1.35)),
    Destination("malaysia", "Malaysia", "Malaysia", "MY", "MYR", "Malaysian Ringgit", "🇲🇾", "Asia", "MYS", "458"),
    Destination("philippines", "Philippines", "Philippines", "PH", "PHP", "Philippine Peso", "🇵🇭", "Asia", "PHL", "608"),
    Destination("china", "China", "China", "CN", "CNY", "Chinese Yuan", "🇨🇳", "Asia", "CHN", "156"),
    Destination("hong-kong", "Hong Kong", "Hong Kong", "HK", "HKD", "Hong Kong Dollar", "🇭🇰", "Asia", "HKG", "344", map_point=(114.17, 22.32)),
    Destination("india", "India", "India", "IN", "INR", "Indian Rupee", "🇮🇳", "Asia", "IND", "356"),
    # Middle East
    Destination("uae", "United Arab Emirates", "United Arab Emirates", "AE", "AED", "UAE Dirham", "🇦🇪", "Middle East", "ARE", "784"),
    Destination("turkey", "Türkiye", "Türkiye", "TR", "TRY", "Turkish Lira", "🇹🇷", "Europe", "TUR", "792"),
    # Europe
    Destination("united-kingdom", "United Kingdom", "United Kingdom", "GB", "GBP", "Pound Sterling", "🇬🇧", "Europe", "GBR", "826"),
    Destination("france", "France", "France", "FR", "EUR", "Euro", "🇫🇷", "Europe", "FRA", "250"),
    Destination("italy", "Italy", "Italy", "IT", "EUR", "Euro", "🇮🇹", "Europe", "ITA", "380"),
    Destination("spain", "Spain", "Spain", "ES", "EUR", "Euro", "🇪🇸", "Europe", "ESP", "724"),
    Destination("greece", "Greece", "Greece", "GR", "EUR", "Euro", "🇬🇷", "Europe", "GRC", "300"),
    Destination("switzerland", "Switzerland", "Switzerland", "CH", "CHF", "Swiss Franc", "🇨🇭", "Europe", "CHE", "756"),
    # Americas
    Destination("united-states", "United States", "United States", "US", "USD", "US Dollar", "🇺🇸", "Americas", "USA", "840"),
    Destination("canada", "Canada", "Canada", "CA", "CAD", "Canadian Dollar", "🇨🇦", "Americas", "CAN", "124"),
    Destination("mexico", "Mexico", "Mexico", "MX", "MXN", "Mexican Peso", "🇲🇽", "Americas", "MEX", "484"),
    # Oceania
    Destination("new-zealand", "New Zealand", "New Zealand", "NZ", "NZD", "New Zealand Dollar", "🇳🇿", "Oceania", "NZL", "554"),
    Destination("australia", "Australia", "Australia", "AU", "AUD", "Australian Dollar", "🇦🇺", "Oceania", "AUS", "036"),
    Destination("fiji", "Fiji", "Fiji", "FJ", "FJD", "Fijian Dollar", "🇫🇯", "Oceania", "FJI", "242"),
    # Africa
    Destination("south-africa", "South Africa", "South Africa", "ZA", "ZAR", "South African Rand", "🇿🇦", "Africa", "ZAF", "710"),
    Destination("egypt", "Egypt", "Egypt", "EG", "EGP", "Egyptian Pound", "🇪🇬", "Africa", "EGY", "818"),
)

HOME_CURRENCIES: tuple[HomeCurrency, ...] = (
    HomeCurrency("AUD", "Australian Dollar", "Australia", "Australia", "🇦🇺", "AUS"),
    HomeCurrency("USD", "US Dollar", "United States", "United States", "🇺🇸", "USA"),
    HomeCurrency("GBP", "Pound Sterling", "United Kingdom", "United Kingdom", "🇬🇧", "GBR"),
    HomeCurrency("EUR", "Euro", "Eurozone", "Eurozone", "🇪🇺", "G163", cpi_index="HICP"),
    HomeCurrency("SGD", "Singapore Dollar", "Singapore", "Singapore", "🇸🇬", "SGP"),
    HomeCurrency("NZD", "New Zealand Dollar", "New Zealand", "New Zealand", "🇳🇿", "NZL"),
    HomeCurrency("CAD", "Canadian Dollar", "Canada", "Canada", "🇨🇦", "CAN"),
)

PERIODS: tuple[Period, ...] = (
    Period("1y", "Past 1 year", 1),
    Period("3y", "Past 3 years", 3),
    Period("5y", "Past 5 years", 5),
    Period("10y", "Past 10 years", 10),
)

DEFAULT_BASE = "AUD"
DEFAULT_PERIOD = "5y"


def enabled_destinations() -> list[Destination]:
    return [d for d in DESTINATIONS if d.enabled]


def get_destination(key: str) -> Destination | None:
    """Look a destination up by slug ("japan") or ISO alpha-2 code ("JP")."""
    key = key.strip().lower()
    for d in enabled_destinations():
        if d.id == key or d.iso2.lower() == key:
            return d
    return None


def get_home_currency(code: str) -> HomeCurrency | None:
    code = code.strip().upper()
    return next((h for h in HOME_CURRENCIES if h.code == code), None)


def get_period(key: str) -> Period | None:
    key = key.strip().lower()
    return next((p for p in PERIODS if p.key == key), None)


def all_currency_codes() -> list[str]:
    """Every currency the app needs FX history for (destinations + home currencies)."""
    codes = {d.currency_code for d in enabled_destinations()} | {h.code for h in HOME_CURRENCIES}
    return sorted(codes)


def all_cpi_series() -> list[tuple[str, str]]:
    """Every (cpi_code, cpi_index) pair needed for inflation adjustment."""
    pairs = {(d.cpi_code, d.cpi_index) for d in enabled_destinations()}
    pairs |= {(h.cpi_code, h.cpi_index) for h in HOME_CURRENCIES}
    return sorted(pairs)
