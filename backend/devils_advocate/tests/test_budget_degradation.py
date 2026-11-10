"""When the retrieval budget runs short, trial verification degrades instead of failing."""
import copy

from devils_advocate.http_client import JsonClient
from devils_advocate.investigation import default_budget_seconds
from devils_advocate.models import TargetInput
from devils_advocate.trial_retriever import retrieve_trials
from devils_advocate.tests.test_stop_reasons import record

TARGET = TargetInput(disease_name="Alzheimer's disease", target_symbol='BACE1')


def study(nct, status):
    r = copy.deepcopy(record())
    r['protocolSection']['identificationModule']['nctId'] = nct
    r['protocolSection']['statusModule']['overallStatus'] = status
    r['protocolSection']['statusModule'].pop('whyStopped', None)
    return r


class BudgetClient:
    def __init__(self, search, remaining):
        self.search, self.remaining, self.fetched = search, remaining, []

    def remaining_seconds(self):
        return self.remaining

    def get(self, url, params=None):
        if params is not None:
            return self.search
        self.fetched.append(url.rsplit('/', 1)[-1])
        return study(self.fetched[-1], 'TERMINATED')


def test_stopped_trials_are_verified_first_and_the_rest_are_left_unverified_when_time_is_short():
    search = {'studies': [study('NCT00000001', 'COMPLETED'), study('NCT00000002', 'TERMINATED'), study('NCT00000003', 'RECRUITING')]}
    client = BudgetClient(search, remaining=5)  # below the reserve: no time for full records
    notes = []
    trials = {t.nct_id: t for t in retrieve_trials(client, TARGET, [], notes)}
    assert client.fetched == []
    assert all(not t.stop_reason.full_record_checked for t in trials.values())
    assert any('time budget' in n for n in notes) and len(trials) == 3


def test_full_records_are_fetched_stopped_first_when_time_allows():
    search = {'studies': [study('NCT00000001', 'COMPLETED'), study('NCT00000002', 'TERMINATED'), study('NCT00000003', 'WITHDRAWN')]}
    client = BudgetClient(search, remaining=1000)
    trials = retrieve_trials(client, TARGET, [], [])
    assert client.fetched[:2] == ['NCT00000002', 'NCT00000003'] and len(client.fetched) == 3
    assert all(t.stop_reason.full_record_checked for t in trials)


def test_remaining_seconds_is_none_outside_tracking_and_counts_down_inside():
    client = JsonClient()
    assert client.remaining_seconds() is None
    with client.tracking(None, budget_seconds=100):
        assert 99 < client.remaining_seconds() <= 100


def test_default_budget_leaves_room_for_claude(monkeypatch):
    monkeypatch.delenv('RESEARCH_RETRIEVAL_BUDGET_SECONDS', raising=False)
    assert default_budget_seconds(use_ai=False) == 240 and default_budget_seconds(use_ai=True) == 150
    monkeypatch.setenv('RESEARCH_RETRIEVAL_BUDGET_SECONDS', '60')
    assert default_budget_seconds(use_ai=False) == 60 and default_budget_seconds(use_ai=True) == 60
