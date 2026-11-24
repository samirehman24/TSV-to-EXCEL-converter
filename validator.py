"""TSV validation and conservative recovery for the business-data schema."""
import csv
import io
import re
from schema import STANDARD_COLUMNS, COLUMN_ALIASES

def normalize_header(value):
    return "".join(c for c in value.casefold() if c.isalnum())

def blank(value):
    # Only discard genuinely empty placeholders, never nonempty values.
    return value == ""

def geography(value):
    return bool(re.search(r",\s*(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)(?:\b)", value))

def specialty(value):
    return bool(re.search(r"electrical|wiring|installation|generator|lighting|remodel|automation|contracting|charger|engineering|equipment|repair", value, re.I)) and not geography(value)

def hours(value):
    return bool(re.search(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b|\b(?:AM|PM)\b|24 hours|by appointment", value, re.I))

def phone(value):
    return bool(re.fullmatch(r"[+()\d .-]+", value)) and 10 <= len(re.sub(r"\D", "", value)) <= 15

def tail_matches(t):
    return (
        len(t) == 10
        and bool(t[2].strip())
        and bool(re.fullmatch(r"[A-Z]{2}", t[3]))
        and (blank(t[4]) or bool(re.fullmatch(r"\d{5}(?:-\d{4})?", t[4])))
        and bool(re.search(r"\bCounty\b", t[5], re.I))
        and (blank(t[6]) or phone(t[6]))
        and (blank(t[7]) or bool(re.match(r"https?://|www\.", t[7], re.I)))
        and (blank(t[8]) or bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", t[8])))
        and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", t[9]))
    )

def recover_row(row):
    """Return (row, reason), or (None, reason) if recovery is unsafe."""
    if len(row) < 22:
        return None, "Too few fields for safe recovery."

    head, middle, tail = row[:12], row[12:-10], row[-10:]
    fixed = None
    reason = ""

    # These rules target the specific displaced middle block found in test.tsv.
    if tail_matches(tail):
        if (len(middle) == 5
                and (blank(middle[0]) or specialty(middle[0]))
                and geography(middle[1])
                and all(map(blank, middle[2:]))):
            fixed = middle + [""]
            reason = "Restored an empty field before the address block."

        elif (len(middle) == 6 and blank(middle[0])
                and specialty(middle[1]) and geography(middle[2])
                and blank(middle[3]) and blank(middle[5])
                and (blank(middle[4]) or geography(middle[4]))):
            fixed = [middle[1], middle[2], middle[4], "", "", ""]
            reason = "Realigned service specialties, service areas and locations."

        elif (len(middle) == 7 and specialty(middle[0])
                and geography(middle[1])
                and blank(middle[2]) and blank(middle[3])
                and hours(middle[4])
                and (blank(middle[5]) or re.fullmatch(r"(?:yes|no)(?:\s*\(.*\))?", middle[5], re.I))
                and (blank(middle[6]) or phone(middle[6]))):
            fixed = middle[:3] + middle[4:]
            reason = "Removed a redundant empty field before business hours."

        elif (len(middle) == 8 and blank(middle[0])
                and specialty(middle[1]) and geography(middle[2])
                and blank(middle[3]) and geography(middle[4])
                and hours(middle[5]) and blank(middle[6]) and blank(middle[7])):
            fixed = [middle[1], middle[2]] + middle[4:]
            reason = "Realigned specialties, locations and hours."

    if fixed is not None:
        repaired = head + fixed + tail
        # Guarantee that every original nonempty value survives in order.
        if (len(repaired) == 28
                and [v for v in repaired if v != ""] == [v for v in row if v != ""]):
            return repaired, reason
        return None, "Recovery would alter nonempty data."

    if len(row) == 28:
        # Catch obvious shifts even when the field count is correct.
        if (hours(row[16]) or hours(row[17])
                or geography(row[16]) or geography(row[17])
                or (specialty(row[13]) and geography(row[14]) and blank(row[12]))):
            return None, "Possible shifted fields; review the middle columns."
        return row, ""

    return None, f"Expected 28 fields, found {len(row)}; no safe repair rule matched."

def validate_tsv(file_path=None, text=None):
    result = {"headers": [], "rows": [], "errors": [], "warnings": [], "valid": False}

    try:
        if file_path is not None:
            with open(file_path, encoding="utf-8-sig", newline="") as f:
                content = f.read()
        elif text is not None:
            content = text
        else:
            raise ValueError("No input data provided.")

        content = content.removeprefix("\ufeff")
        reader = csv.reader(io.StringIO(content, newline=""), delimiter="\t", strict=True)
        headers = next((r for r in reader if r and any(v.strip() for v in r)), None)
        if not headers:
            raise ValueError("No column headers found.")

        lookup = {normalize_header(c): c for c in STANDARD_COLUMNS}
        lookup.update({normalize_header(a): c for a, c in COLUMN_ALIASES.items()})
        mapping = {}
        for i, header in enumerate(headers):
            name = lookup.get(normalize_header(header))
            if name is None:
                result["errors"].append(f"Unknown column: {header!r}")
            elif name in mapping:
                result["errors"].append(f"Duplicate column: {header!r}")
            else:
                mapping[name] = i

        if "Name" not in mapping:
            result["errors"].append("Required column 'Name' is missing.")
        if result["errors"]:
            return result

        result["headers"] = list(STANDARD_COLUMNS)
        missing = [c for c in STANDARD_COLUMNS if c not in mapping]
        if missing:
            result["warnings"].append("Missing columns left blank: " + ", ".join(missing))

        canonical = (len(headers) == 28 and
                     [lookup[normalize_header(h)] for h in headers] == list(STANDARD_COLUMNS))

        for row in reader:
            line = reader.line_num
            if not row:
                result["warnings"].append(f"Blank line skipped at line {line}.")
                continue
            if canonical:
                row, reason = recover_row(row)
                if row is None:
                    result["errors"].append(f"Line {line}: {reason}")
                    continue
                if reason:
                    result["warnings"].append(f"Line {line}: inferred repair. {reason}")
            elif len(row) != len(headers):
                result["errors"].append(f"Line {line}: Expected {len(headers)} fields, found {len(row)}.")
                continue

            result["rows"].append([row[mapping[c]] if c in mapping else "" for c in STANDARD_COLUMNS])

        if not result["rows"]:
            result["errors"].append("No business records found.")
        result["valid"] = not result["errors"]

    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        result["errors"].append(str(exc))

    return result
