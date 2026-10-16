import pytest

from worldline import geo
from worldline.reference import FAMILIES, ROOT_FAMILY, ROOTS, actor_country, base_code_label, fips_to_iso3, place_name, places


def test_fips_and_actor_codes_map_to_iso3():
    fips = fips_to_iso3()
    assert fips["US"] == "USA" and fips["UK"] == "GBR" and fips["RS"] == "RUS" and fips["UP"] == "UKR"
    assert fips["GZ"] == "PSE" and fips["WE"] == "PSE"  # Gaza and the West Bank are reported separately by GDELT
    assert actor_country("USA") == "USA" and actor_country("WSB") == "PSE" and actor_country("ROM") == "ROU"
    assert actor_country("AFR") is None and actor_country("") is None
    assert place_name("CIV") and places()["SDN"].continent == "Africa"


def test_every_cameo_root_has_exactly_one_family():
    assert sorted(ROOT_FAMILY) == ROOTS
    assert sorted(r for f in FAMILIES for r in f["roots"]) == ROOTS
    assert base_code_label("190")


def test_equal_earth_projection():
    assert geo.equal_earth(0, 0) == pytest.approx((0.0, 0.0))
    x_east, _ = geo.equal_earth(180, 0)
    x_west, _ = geo.equal_earth(-180, 0)
    assert x_east == pytest.approx(-x_west) and geo.equal_earth(0, 90)[1] > 0
    assert geo.to_screen(-180, 0)[0] == pytest.approx(0.0) and geo.to_screen(180, 0)[0] == pytest.approx(geo.WIDTH)
    assert geo.to_screen(0, 90)[1] == pytest.approx(0.0)
    assert geo.to_screen(-180, 90)[0] > 0  # Equal Earth draws the poles as lines shorter than the equator


def test_rings_crossing_the_antimeridian_are_split():
    ring = [(170.0, 10.0), (-170.0, 10.0), (-170.0, 20.0), (170.0, 20.0), (170.0, 10.0)]
    parts = geo.split_antimeridian(ring)
    assert len(parts) == 2
    for part in parts:
        longitudes = [lon for lon, _ in part]
        assert max(longitudes) - min(longitudes) <= 180


def test_map_has_every_monitored_country_shape():
    shapes = geo.build_map()
    countries = shapes["countries"]
    assert {"USA", "RUS", "FJI", "SDN", "PSE", "UKR"} <= set(countries) and "ATA" not in countries
    assert all(c["d"].startswith("M") and c["d"].endswith("Z") for c in countries.values())
    assert all(0 <= c["c"][0] <= geo.WIDTH and 0 <= c["c"][1] <= shapes["height"] for c in countries.values())
    assert shapes["width"] == geo.WIDTH and 0 < shapes["height"] < geo.WIDTH
