from datetime import datetime
import calendar
import os 
import sys 
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.models import ExpiryMonth

def parse_expiry_string(expiry_str: str) -> str:
    """
    Parses expiry strings into yyyy-mm-dd format.

    Supports:
    - '7TH OCT'
    - '05 NOV'
    - '16OCT25'
    - 'OCT'
    - 'DEC'
    - 'OCT25' (same as 'OCT')
    """
    expiry_str = expiry_str.strip().upper()
    today = datetime.today()
    current_year = today.year
    current_month = today.month

    # --- 1. Handle compact format: 16OCT25 ---
    try:
        if len(expiry_str) == 7 and expiry_str[:2].isdigit():
            day = int(expiry_str[:2])
            month_str = expiry_str[2:5]
            year = int("20" + expiry_str[5:])
            month = datetime.strptime(month_str, "%b").month
            return datetime(year, month, day).strftime("%Y-%m-%d")
    except Exception:
        pass

    parts = expiry_str.split()

    # --- 2. Handle Day + Month + (optional year): '7TH OCT', '05 NOV' ---
    if len(parts) >= 2:
        try:
            day_str = parts[0].rstrip("STNDRDTH")  # Remove suffix like 7TH → 7
            day = int(day_str)
            month = datetime.strptime(parts[1], "%b").month
            year = current_year
            if len(parts) == 3 and parts[2].isdigit():
                year = int("20" + parts[2])
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except Exception:
            pass

    # --- 3. Handle Month-only: 'OCT', 'OCT25', 'DEC' ---
    try:
        # Remove year from 'OCT25' to treat like 'OCT'
        if len(expiry_str) > 3 and expiry_str[:3].isalpha():
            month_str = expiry_str[:3]
        else:
            month_str = expiry_str

        input_month = datetime.strptime(month_str, "%b").month

        # Map input month to current / next / next-to-next
        if input_month == current_month:
            return ExpiryMonth.CURRENT
        elif input_month == (current_month % 12) + 1:
            return ExpiryMonth.NEXT
        elif input_month == ((current_month + 1) % 12) + 1:
            return ExpiryMonth.NEXT2NEXT
        else:
            raise ValueError(f"Month '{month_str}' is not within expected 3-month range.")
    except Exception:
        raise ValueError(f"Unrecognized expiry format: '{expiry_str}'")



def run_tests():
    
    test_cases = [
        # (input_string, expected_output)
        ("7TH OCT", "2025-10-07"),
        ("16OCT25", "2025-10-16"),
        ("05 NOV", "2025-11-05"),
        ("OCT", ExpiryMonth.CURRENT),       # current month
        ("NOV", ExpiryMonth.NEXT),       # next month
        ("DEC", ExpiryMonth.NEXT2NEXT),       # next-to-next
        ("OCT25",  ExpiryMonth.CURRENT),     # treated like OCT
        ("DEC25", ExpiryMonth.NEXT2NEXT),     # treated like DEC
        ("N0V", None),               # invalid month (typo)
        ("INVALID", None),           # completely invalid
    ]

    passed = 0
    failed = 0

    for symbol, expected in test_cases:
        try:
            result = parse_expiry_string(symbol)
            if result == expected:
                print(f"✅ PASS: {symbol} → {result}")
                passed += 1
            else:
                print(f"❌ FAIL: {symbol} → {result} (Expected: {expected})")
                failed += 1
        except Exception as e:
            if expected is None:
                print(f"✅ PASS: {symbol} raised expected error → {str(e)}")
                passed += 1
            else:
                print(f"❌ FAIL: {symbol} → Exception: {e} (Expected: {expected})")
                failed += 1

    print(f"\nTest Summary: ✅ {passed} passed, ❌ {failed} failed")

if __name__ == "__main__":
    run_tests()
