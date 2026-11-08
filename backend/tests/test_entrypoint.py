import importlib
import sys


def test_app_module_exposes_workbench_routes(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUT_DATA_DIR", str(tmp_path))
    sys.modules.pop("app", None)
    module = importlib.import_module("app")
    rules = {rule.rule for rule in module.app.url_map.iter_rules()}
    assert "/api/investigations" in rules and "/api/research-decisions" in rules and "/api/screen" in rules
    assert "/api/<path:legacy>" in rules  # scout/health/rationale forwarded to the Scout app


def test_app_module_loads_by_file_path_without_backend_on_sys_path(tmp_path, monkeypatch):
    """Vercel imports the entrypoint by path from another cwd; backend/ is not on sys.path."""
    import importlib.util
    from pathlib import Path
    backend = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("SCOUT_DATA_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if Path(p or ".").resolve() != backend])
    for name in [m for m in sys.modules if m == "app" or m.startswith(("devils_advocate", "pipeline"))]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    spec = importlib.util.spec_from_file_location("vercel_entry", backend / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "/api/investigations" in {rule.rule for rule in module.app.url_map.iter_rules()}
