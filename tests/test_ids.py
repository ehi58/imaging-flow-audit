"""Identifiers: NPI check digits, payer member-ID schemes, accession formats.

The NPI check digit is the Luhn algorithm over the 10 digits with the constant
prefix 80840 (the ISO health-industry prefix), per the CMS NPI check-digit
specification. 1234567893 is the worked example in that specification.
"""
import pytest

from flow import ids


def test_npi_check_digit_matches_the_cms_worked_example():
    assert ids.npi_check_digit("123456789") == 3


def test_valid_npi_accepts_the_worked_example_and_rejects_a_changed_digit():
    assert ids.is_valid_npi("1234567893")
    assert not ids.is_valid_npi("1234567894")


def test_valid_npi_rejects_wrong_lengths_and_non_digits():
    assert not ids.is_valid_npi("123456789")
    assert not ids.is_valid_npi("12345678931")
    assert not ids.is_valid_npi("12345O7893")


def test_make_npi_is_deterministic_and_valid():
    import random

    a = ids.make_npi(random.Random(7))
    b = ids.make_npi(random.Random(7))
    assert a == b
    assert len(a) == 10 and ids.is_valid_npi(a)


def test_make_npi_starts_with_the_reserved_two_prefix():
    # Two of 70 generated 1-prefix NPIs were real, assigned numbers (NPPES check,
    # 2026-11-01). The 2 prefix is valid and essentially unassigned.
    import random

    rng = random.Random(1)
    assert all(ids.make_npi(rng)[0] == "2" for _ in range(200))


def test_member_id_follows_the_payer_scheme_and_checks():
    import random

    scheme = ids.MemberIdScheme(prefix="MAA", digits=8)
    mid = ids.make_member_id(scheme, random.Random(3))
    assert mid.startswith("MAA") and len(mid) == 3 + 8
    assert ids.is_valid_member_id(mid, scheme)


def test_member_id_with_a_bad_check_digit_is_rejected():
    scheme = ids.MemberIdScheme(prefix="MAA", digits=8)
    good = ids.make_member_id(scheme, __import__("random").Random(3))
    last = int(good[-1])
    bad = good[:-1] + str((last + 1) % 10)
    assert not ids.is_valid_member_id(bad, scheme)


def test_member_id_with_another_payers_prefix_is_rejected():
    scheme_a = ids.MemberIdScheme(prefix="MAA", digits=8)
    scheme_b = ids.MemberIdScheme(prefix="MAB", digits=8)
    mid = ids.make_member_id(scheme_a, __import__("random").Random(5))
    assert not ids.is_valid_member_id(mid, scheme_b)


def test_member_id_never_has_the_mbi_shape():
    # An MBI is 11 characters, starts with a digit 1-9, and mixes letters and
    # digits in fixed positions. Every scheme here starts with three letters.
    import random

    for prefix in ("MFS", "MAA", "MCD", "CPA"):
        mid = ids.make_member_id(ids.MemberIdScheme(prefix=prefix, digits=9), random.Random(2))
        assert not ids.looks_like_mbi(mid)
    assert ids.looks_like_mbi("1EG4TE5MK73")


def test_accession_format():
    import random

    acc = ids.make_accession(random.Random(1), 1)
    assert acc.startswith("ACC") and len(acc) == 11 and acc[3:].isdigit()
    assert ids.make_accession(random.Random(1), 1) == acc
    assert ids.make_accession(random.Random(1), 2) != acc
