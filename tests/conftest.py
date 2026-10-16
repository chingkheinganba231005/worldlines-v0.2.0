"""Shared fixtures. Synthetic data follows the real day-record schema (see tests/synthetic.py)."""
import pytest

from synthetic import make_records


@pytest.fixture(scope="session")
def synthetic():
    return make_records()


@pytest.fixture(scope="session")
def synthetic_spike():
    """Sudan's coverage jumps six-fold with 45% violence on day 410, and stays elevated on day 411."""
    return make_records(spikes=[(410, "SU", 6.0, 0.45), (411, "SU", 4.0, 0.40)])
