import pytest

from finsight.schemas import Financials, FilingMeta, Provenance, Sourced


def S(value, prior=None, page=1):
    return Sourced(value=value, prior=prior, prov=Provenance(page=page, modality="text_table", verbatim=str(value)))


@pytest.fixture
def make_fs():
    def _make(**items):
        meta = FilingMeta(company="TestCo", currency="USD", unit_scale="millions", period_end="2025-12-31")
        return Financials(meta=meta, **{k: (v if not isinstance(v, (int, float)) else S(v)) for k, v in items.items()})
    return _make


@pytest.fixture
def S_():
    return S
