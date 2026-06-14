import copy

from video_passage_pipeline import content_hash, projected_route, validation_errors


def manifest():
    return {
        "schema_version": 1,
        "project": {
            "episode_id": "DBT_TEST",
            "title": "Test",
            "location_label": "KANAZAWA · ISHIKAWA",
        },
        "source": {"video": __file__, "duration_s": 10, "gps_csv": "", "gpx": "", "fit": ""},
        "design": {"preset": "video-passage-v1"},
        "telemetry": [
            {"time_s": 0, "lat": 36.0, "lon": 136.0, "speed_kmh": 10},
            {"time_s": 10, "lat": 37.0, "lon": 137.0, "speed_kmh": 20},
        ],
        "cues": [{
            "id": "cue-001", "start_s": 0, "end_s": 10, "place": "湊四丁目",
            "road": "", "eyebrow": "", "copy_horizontal": "物流の拠点が集まる 金沢港の一角へ",
            "copy_vertical": ["物流の拠点が集まる", "金沢港の一角へ"], "review_note": "",
        }],
    }


def test_valid_manifest():
    assert validation_errors(manifest()) == []


def test_rejects_punctuation_and_wording_drift():
    data = manifest()
    data["cues"][0]["copy_horizontal"] = "物流の拠点が集まる、金沢港の一角へ"
    assert len(validation_errors(data)) == 2


def test_content_hash_changes_with_copy():
    first = manifest()
    second = copy.deepcopy(first)
    second["cues"][0]["copy_horizontal"] += " "
    assert content_hash(first) != content_hash(second)


def test_projected_route_stays_in_box():
    points = projected_route(manifest()["telemetry"], (10, 20, 110, 220))
    assert points == [(10.0, 220.0), (110.0, 20.0)]
