from dji_gps_pipeline import (
    collapse_segments,
    downsample_one_hz,
    records_from_exiftool,
    srt_timestamp,
)


def test_records_from_exiftool_orders_copy_groups():
    data = {
        "Copy1:SampleTime": 1.1,
        "Copy1:GPSDateTime": "2026:06:09 18:18:25",
        "Copy1:GPSLatitude": 36.2,
        "Copy1:GPSLongitude": 136.2,
        "Copy1:GPSAltitude": 20,
        ":SampleTime": 0.4,
        ":GPSDateTime": "2026:06:09 18:18:24",
        ":GPSLatitude": 36.1,
        ":GPSLongitude": 136.1,
        ":GPSAltitude": 10,
    }
    rows = records_from_exiftool(data)
    assert [row["sample_time_s"] for row in rows] == [0.4, 1.1]


def test_downsample_one_hz_keeps_first_sample():
    rows = [
        {"sample_time_s": 0.4},
        {"sample_time_s": 0.8},
        {"sample_time_s": 1.1},
    ]
    assert downsample_one_hz(rows) == [rows[0], rows[2]]


def test_collapse_short_leading_segment():
    points = [
        {"sample_time_s": 0, "place": "A", "road": ""},
        {"sample_time_s": 10, "place": "B", "road": "Road"},
        {"sample_time_s": 50, "place": "B", "road": "Road"},
    ]
    assert collapse_segments(points, 80, 30) == [{
        "start": 0,
        "end": 80,
        "label": ("B", "Road"),
    }]


def test_srt_timestamp():
    assert srt_timestamp(65.432) == "00:01:05,432"
