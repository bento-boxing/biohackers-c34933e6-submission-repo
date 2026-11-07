"""Stage 2 pure functions: collapse activities per molecule and rank."""
from __future__ import annotations

from pipeline.models import Compound


def best_per_molecule(activities: list[dict]) -> dict[str, tuple[float, str | None]]:
    best: dict[str, tuple[float, str | None]] = {}
    for a in activities:
        v = a.get("pchembl_value")
        if v is None:
            continue
        p = float(v)
        mid = a["molecule_chembl_id"]
        if mid not in best or p > best[mid][0]:
            best[mid] = (p, a.get("assay_type"))
    return best


def _f(x) -> float | None:
    return None if x is None else float(x)


def _i(x) -> int | None:
    return None if x is None else int(x)


def build_compounds(best: dict[str, tuple[float, str | None]], mols: dict[str, dict]) -> list[Compound]:
    out = []
    for mid, (p, assay) in best.items():
        m = mols.get(mid) or {}
        props = m.get("molecule_properties") or {}
        out.append(Compound(
            chembl_id=mid, name=m.get("pref_name"), best_pchembl=p, assay_type=assay,
            max_phase=m.get("max_phase"), mw=_f(props.get("full_mwt")), alogp=_f(props.get("alogp")),
            hbd=_i(props.get("hbd")), hba=_i(props.get("hba")), psa=_f(props.get("psa")),
            ro5_violations=_i(props.get("num_ro5_violations")),
        ))
    return out


def rank_compounds(compounds: list[Compound]) -> list[Compound]:
    return sorted(compounds, key=lambda c: (-c.best_pchembl,
                                            c.ro5_violations if c.ro5_violations is not None else 99,
                                            c.chembl_id))
