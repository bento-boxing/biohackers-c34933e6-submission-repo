import pytest

from pipeline.models import Weights
from pipeline.scout.pipeline import rescore
from pipeline.scout.restore import result_from_run_json
from tests.test_api import api, scout  # noqa: F401  (fixture + helper)


def test_round_trip_scout_json_rebuilds_identical_components(api):
    run = scout(api).get_json()
    rebuilt = rescore(result_from_run_json(run), Weights(**run["default_weights"]))
    assert [t.evidence.symbol for t in rebuilt.targets] == [t["symbol"] for t in run["targets"]]
    for posted, t in zip(run["targets"], rebuilt.targets):
        for key, value in posted["components"].items():
            assert abs(getattr(t.scores, key) - value) < 1e-6, (posted["symbol"], key)
    assert rebuilt.disease.id == run["disease"]["id"]


def test_missing_evidence_raises():
    with pytest.raises(ValueError):
        result_from_run_json({"disease": {"id": "X", "name": "x"}, "targets": [{"symbol": "GENE"}]})
