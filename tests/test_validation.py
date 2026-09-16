from datetime import datetime, timedelta, timezone

from wickhunter.models import Candle
from wickhunter.validation import validate_m1


def candle(minutes):
    return Candle(datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc) + timedelta(minutes=minutes), 100, 101, 99, 100.5)


def test_valid_contiguous_m1_dataset():
    report = validate_m1([candle(0), candle(1), candle(2)])
    assert report.valid
    assert report.candles == 3
    assert report.gaps == 0


def test_gap_is_reported():
    report = validate_m1([candle(0), candle(3)])
    assert not report.valid
    assert report.gaps == 1
    assert report.max_gap_minutes == 3


def test_duplicate_timestamp_is_reported():
    report = validate_m1([candle(0), candle(0)])
    assert not report.valid
    assert report.duplicates == 1


def test_naive_timestamp_is_invalid():
    naive = Candle(datetime(2026, 1, 2, 9, 0), 100, 101, 99, 100.5)
    report = validate_m1([naive])
    assert not report.valid
    assert not report.timezone_aware
