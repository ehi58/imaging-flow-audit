"""Identifiers used across the flow.

NPI check digit: the Luhn formula over the ten-digit NPI with the constant
prefix 80840 prepended, as the CMS NPI check-digit specification describes.
The worked example in that document is 1234567893.

Member IDs: each synthetic payer has its own scheme, a three-letter prefix and
a digit count whose last digit is a Luhn check digit over the digits. None of
them has the shape of a Medicare Beneficiary Identifier, so a random synthetic
ID can never collide with a real beneficiary's number.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass

NPI_PREFIX = "80840"


def _luhn_sum(digits: str) -> int:
    """Luhn sum of a digit string where the RIGHTMOST digit is doubled."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total


def npi_check_digit(first_nine: str) -> int:
    if not re.fullmatch(r"\d{9}", first_nine):
        raise ValueError("an NPI body is nine digits")
    return (10 - _luhn_sum(NPI_PREFIX + first_nine) % 10) % 10


def is_valid_npi(npi: str) -> bool:
    if not isinstance(npi, str) or not re.fullmatch(r"\d{10}", npi):
        return False
    return npi_check_digit(npi[:9]) == int(npi[9])


def make_npi(rng: random.Random) -> str:
    """A Luhn-valid NPI whose first digit is 2.

    NPIs begin with 1 or 2, and in practice NPPES assigns from the 1 range: of 70
    generated NPIs checked against the registry on 2026-11-01, two that began
    with 1 were real, assigned numbers and none that began with 2 were. The 2
    prefix keeps the shape and makes a collision with a real provider remote;
    scripts/check_nppes.py still proves every committed NPI absent.
    """
    body = "2" + "".join(rng.choice("0123456789") for _ in range(8))
    return body + str(npi_check_digit(body))


@dataclass(frozen=True)
class MemberIdScheme:
    prefix: str
    digits: int


def _digits_check(digits_without_check: str) -> int:
    return (10 - _luhn_sum(digits_without_check) % 10) % 10


def make_member_id(scheme: MemberIdScheme, rng: random.Random) -> str:
    body = "".join(rng.choice("0123456789") for _ in range(scheme.digits - 1))
    return scheme.prefix + body + str(_digits_check(body))


def is_valid_member_id(member_id: str, scheme: MemberIdScheme) -> bool:
    if not isinstance(member_id, str) or not member_id.startswith(scheme.prefix):
        return False
    digits = member_id[len(scheme.prefix) :]
    if not re.fullmatch(r"\d{%d}" % scheme.digits, digits):
        return False
    return _digits_check(digits[:-1]) == int(digits[-1])


# MBI: 11 characters; C = digit 1-9, A = letter excluding S L O I B Z,
# AN = A or digit, N = digit. Pattern: C A AN N A AN N A A N N.
_MBI = re.compile(r"^[1-9][AC-HJKMNP-RT-Y][AC-HJKMNP-RT-Y0-9]\d[AC-HJKMNP-RT-Y][AC-HJKMNP-RT-Y0-9]\d[AC-HJKMNP-RT-Y]{2}\d{2}$")


def looks_like_mbi(value: str) -> bool:
    return bool(_MBI.match(value or ""))


def make_accession(rng: random.Random, n: int) -> str:
    base = rng.randrange(10**7)
    return f"ACC{(base * 10 + n) % 10**8:08d}"
