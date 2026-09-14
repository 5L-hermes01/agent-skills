import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import publish_deals as P


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(P, "seen_listings_db", {})
    monkeypatch.setattr(P, "details_cache", {})
    monkeypatch.setattr(P.time, "sleep", lambda _: None)


@pytest.mark.parametrize("field", ["exterior_color", "exteriorColor", "color", "paint"])
def test_listing_color_fallback(field):
    assert P.get_color_and_options({"vin": "VIN", field: "Wind Chill Pearl"}, None) == "Wind Chill Pearl"


@pytest.mark.parametrize("color,expected", [("Fathom Blue Pearl", "Blue"), ("Velvet Red Pearl", "Red"), ("Wind Chill Pearl", "Pearl")])
def test_pearl_hue(color, expected):
    assert P.abbreviate_color(color) == expected


def test_color_sources(monkeypatch):
    assert P.extract_color({"description": "Heavy Metal"}) == "Heavy Metal"
    assert P.extract_color({"trim": "Nightshade"}) == "TBD"
    monkeypatch.setattr(P.requests, "get", lambda *a, **k: SimpleNamespace(status_code=200, text="Exterior: Cement"))
    assert P.extract_color({"vdp_url": "https://dealer.test/vehicle"}) == "Cement"


@pytest.mark.parametrize("year,expected", [(2026, True), ("2026", True), (2025, False), (None, False), ("bad", False)])
def test_year_filter(year, expected):
    car = {"vin": "VIN", "price": 50000, "inventory_type": "new", "year": year}
    assert P.car_matches_profile(car, "Toyota", "Grand Highlander", "", None, [], False, False, 2026) is expected


@pytest.mark.parametrize("source", ["api", "saved"])
def test_year_passed_to_all_listing_paths(monkeypatch, tmp_path, source):
    target = {"make": "Toyota", "model": "Grand Highlander", "trim": "Limited", "year": 2026}
    cars = [{**target, "vin": str(year), "year": year, "price": 50000, "inventory_type": "new"} for year in (2025, 2026)]
    if source == "saved":
        (tmp_path / "data").mkdir()
        (tmp_path / "data/comprehensive_search_results.json").write_text(json.dumps({"cars": cars}))
    else:
        pages = iter([cars, []])
        monkeypatch.setattr(P.requests, "get", lambda *a, **k: SimpleNamespace(status_code=200, json=lambda: {"data": next(pages)}))
    result = P.get_listings_for_trim(target, "fake" if source == "api" else None, str(tmp_path))
    assert [c["year"] for c in result] == [2026]


@pytest.mark.parametrize("seen", [False, True])
def test_bulletin_urls_benchmark_and_format(monkeypatch, tmp_path, capsys, seen):
    config = tmp_path / "profiles.json"
    config.write_text(json.dumps([{"make": "Toyota", "model": "Grand Highlander", "trim": "Limited", "target_otd_price": 58450.85}]))
    monkeypatch.setattr(sys, "argv", ["publish_deals.py", "--trims", str(config)])
    monkeypatch.setattr(P, "load_dotenv", lambda *a: None)
    monkeypatch.setattr(P, "seed_details_cache", lambda *a: None)
    monkeypatch.setattr(P, "load_seen_listings", lambda *a: {"a", "b", "c"} if seen else set())
    saved = []
    monkeypatch.setattr(P, "save_seen_listings", lambda vins, path: saved.append(vins))
    cars = [{"vin": vin, "price": 50000 + i, "computed_distance": i + 1,
             "state": "NY", "dealer_name": "Synthetic Dealer",
             "vdp_url": "https://dealer.test/car" if i else ""} for i, vin in enumerate("abc")]
    monkeypatch.setattr(P, "get_listings_for_trim", lambda *a: cars)
    monkeypatch.setattr(P, "get_color_and_options", lambda *a: "Fathom Blue Pearl")
    monkeypatch.setattr(P, "get_features_summary", lambda *a: "C: 3/3 | O: 2/2")
    P.main()
    output = capsys.readouterr().out
    assert "target $58,451" in output
    assert "Benchmark: cheapest active $50,000" in output
    assert "Top 5 Cheapest" not in output
    if seen:
        assert "No new listings appeared" in output
        assert "|" not in output
    else:
        assert "1. N/A\n2. https://dealer.test/car" in output
        rows = [line for line in output.splitlines() if line.startswith("|")]
        assert len(rows) == 4  # header, separator, two closest arrivals
        assert all(len(row.split("|")) == 8 for row in rows)
        assert "3/3,2/2" in output
        assert "Blue" in output
    assert saved == [{"a", "b", "c"}]
