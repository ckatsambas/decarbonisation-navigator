"""Ship size from public MRV data: reference-line inversion, fuel per hour, type range."""
import math

import pytest

from navigator.engine import reference as R
from navigator.engine import sizing


def test_reference_data_matches_study_totals():
    total_2018 = sum(c.value("co2_mt", "2018") for c in R.classes() if "2018" in c.years)
    assert total_2018 == pytest.approx(1056, abs=2)          # Fourth IMO GHG Study: 1,056 Mt CO2 in 2018
    assert len(R.classes()) == 70
    assert R.class_for("bulk", dwt=82_000).size == "60000-99999"
    assert R.class_for("ropax", gt=25_000).size == "20000-+"


def test_index_inversion_round_trip():
    rules = sizing._eedi_rules()
    line = rules["reference_lines"]["bulk"]
    attained = line["a"] * 82_000 ** -line["c"] * (1 - 0.15)   # mid-range reduction
    s = sizing.index_signal("bulk", "EEDI", attained, "dwt")
    assert math.exp(s.mu) == pytest.approx(82_000, rel=1e-6)
    assert sizing.index_signal("container", "EEDI", 10, "dwt") is None      # line too flat to identify size


def test_hour_signal_used_only_where_informative():
    assert sizing.fit_hour("container", "dwt").beta >= sizing.MIN_BETA_HOUR
    assert sizing.hour_signal("oil", "dwt", 5000, 4000) is None


def test_estimate_capacity_ranges():
    e = sizing.estimate_capacity("Bulk carrier", "bulk", 6000, 40_000, 3000, "EEDI", 3.3)
    assert e.low < e.likely < e.high and e.details["unit"] == "dwt" and "index" in e.method
    t = sizing.estimate_capacity("Vehicle carrier", "vehicle", 8000, 60_000, 4000, None, None)
    assert t.method == "type"                                 # only the type range: user should confirm
    assert sizing.estimate_capacity("Ro-ro ship", "roro", 5000, 40_000, 3000, None, None) is None
