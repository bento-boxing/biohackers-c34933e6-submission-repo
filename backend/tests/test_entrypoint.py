import importlib
import sys


def test_app_module_exposes_workbench_routes(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUT_DATA_DIR", str(tmp_path))
    sys.modules.pop("app", None)
    module = importlib.import_module("app")
    rules = {rule.rule for rule in module.app.url_map.iter_rules()}
    assert "/api/investigations" in rules and "/api/research-decisions" in rules and "/api/screen" in rules
    assert "/api/<path:legacy>" in rules  # scout/health/rationale forwarded to the Scout app
