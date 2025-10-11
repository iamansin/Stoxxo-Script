import re
from enum import Enum


class OptionType(Enum):
    CE = "CE"
    PE = "PE"




import re
from enum import Enum


class OptionType(Enum):
    CE = "CE"
    PE = "PE"


def _parse_symbol_details(symbol_str: str) -> tuple[str, str, str, OptionType]:
    """
    Parses option symbol into (index, expiry, strike, option_type).
    
    Supports expiry formats:
    - "7TH OCT"
    - "05 NOV"
    - "16OCT25"
    - "OCT"
    - "OCT25"
    """
    pattern = r"""
        ^\s*
        (?P<index>[A-Z]+)                        # Index
        \s+
        (?:
            (?P<day1>\d{1,2}(?:ST|ND|RD|TH)?)     # Day with suffix (7TH)
            \s+
            (?P<month1>[A-Z]{3})                  # Month (OCT)
            (?:\s*(?P<year1>\d{2}))?              # Optional year
            |
            (?P<compact>\d{1,2}[A-Z]{3}\d{2})     # Compact expiry e.g., 16OCT25
            |
            (?P<month2>[A-Z]{3})(?P<year2>\d{2})? # Month or Month+Year e.g., OCT, OCT25
        )
        \s+
        (?P<strike>\d+)                          # Strike
        \s+
        (?P<option_type>CE|PE|C|P)               # Option Type
        \s*$
    """

    match = re.match(pattern, symbol_str.strip(), re.IGNORECASE | re.VERBOSE)
    if not match:
        raise ValueError(f"Invalid symbol format: {symbol_str}")

    index = match.group("index").upper()

    # Determine which expiry format matched
    if match.group("compact"):
        expiry = match.group("compact").upper()
    elif match.group("day1") and match.group("month1"):
        expiry = f"{match.group('day1').upper()} {match.group('month1').upper()}"
        if match.group("year1"):
            expiry += match.group("year1")
    elif match.group("month2"):
        expiry = match.group("month2").upper()
        if match.group("year2"):
            expiry += match.group("year2")
    else:
        raise ValueError(f"Invalid expiry format in symbol: {symbol_str}")

    strike = match.group("strike")
    opt_raw = match.group("option_type").upper()
    option_type = OptionType.CE if opt_raw in ("CE", "C") else OptionType.PE

    return index, expiry, strike, option_type

# ===========================
# 🚀 Test Cases
# ===========================
test_symbols = [
    "NIFTY 7TH OCT 25900 CE",              # day+month
    "SENSEX 16OCT25 83000 PE",             # compact
    "NIFTY 05 NOV 19600 PE",               # dd mmm
    "BANKNIFTY OCT 43000 CE",              # month only
    "BANKNIFTY OCT25 43000 CE",            # month + year
    "NIFTY   7TH     OCT    25900    CE",  # spaced
]

for symbol in test_symbols:
    try:
        result = _parse_symbol_details(symbol)
        print(f"✅ Parsed: {symbol} -> {result}")
    except ValueError as e:
        print(f"❌ Failed: {symbol} -> {e}")
