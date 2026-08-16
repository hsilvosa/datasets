from datetime import date

from gdelt_events.manifest import archive_period, parse_checksums, parse_sizes


def test_manifest_parsers() -> None:
    assert parse_checksums("abc\n7fb1b6ff781aea3d441abf512dc5e0f9  1979.zip\n") == {
        "1979.zip": "7fb1b6ff781aea3d441abf512dc5e0f9"
    }
    assert parse_sizes("123 1979.zip\n") == {"1979.zip": 123}


def test_archive_period_and_cutoff() -> None:
    cutoff = date(2026, 8, 14)
    assert archive_period("1979.zip", cutoff) == "1979"
    assert archive_period("200601.zip", cutoff) == "200601"
    assert archive_period("20130401.export.CSV.zip", cutoff) == "20130401"
    assert archive_period("20260815.export.CSV.zip", cutoff) is None
    assert archive_period("GDELT.MASTERREDUCEDV2.1979-2013.zip", cutoff) is None
