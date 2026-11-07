"""Open Targets Platform GraphQL client (schema verified 2026-11-07)."""
from __future__ import annotations

from pipeline.http import HttpClient, UpstreamError
from pipeline.models import Disease, SafetyFlag, TargetEvidence

OT_URL = "https://api.platform.opentargets.org/api/v4/graphql"
EXPRESSION_TPM_THRESHOLD = 50.0
SAFETY_TISSUES = ("heart", "liver", "kidney")

SEARCH_QUERY = """
query($q:String!){ search(queryString:$q, entityNames:["disease"], page:{index:0,size:5}){ hits{ id name entity } } }
"""
TARGETS_QUERY = """
query($id:String!,$n:Int!){ disease(efoId:$id){ associatedTargets(page:{index:0,size:$n}){
  rows{ score datatypeScores{ id score }
    target{ id approvedSymbol approvedName tractability{ label modality value } proteinIds{ id source } } } } } }
"""
SAFETY_QUERY = """
query($id:String!){ target(ensemblId:$id){
  safetyLiabilities{ event effects{ direction dosing } biosamples{ tissueLabel } }
  baselineExpression(page:{index:0,size:2000}){ rows{ datasourceId median tissueBiosampleFromSource } } } }
"""


class DiseaseNotFound(Exception):
    pass


def graphql(client: HttpClient, query: str, variables: dict) -> dict:
    data = client.post_json(OT_URL, {"query": query, "variables": variables})
    if data.get("errors"):
        raise UpstreamError("Open Targets error: " + data["errors"][0].get("message", "?"))
    return data["data"]


def resolve_disease(client: HttpClient, name: str) -> Disease:
    hits = graphql(client, SEARCH_QUERY, {"q": name})["search"]["hits"]
    for h in hits:
        if h["entity"] == "disease":
            return Disease(id=h["id"], name=h["name"])
    raise DiseaseNotFound(name)


def _has_approved_drug(tractability: list[dict]) -> bool:
    return any(t["label"] == "Approved Drug" and t["modality"] == "SM" and t["value"]
               for t in tractability)


def associated_targets(client: HttpClient, disease_id: str, n: int) -> list[TargetEvidence]:
    data = graphql(client, TARGETS_QUERY, {"id": disease_id, "n": n})
    rows = data["disease"]["associatedTargets"]["rows"]
    out = []
    for r in rows:
        t = r["target"]
        uniprot = next((p["id"] for p in t.get("proteinIds") or [] if p["source"] == "uniprot_swissprot"), None)
        tract = t.get("tractability") or []
        out.append(TargetEvidence(
            target_id=t["id"], symbol=t["approvedSymbol"], name=t["approvedName"], uniprot=uniprot,
            ot_score=r["score"], datatype_scores={d["id"]: d["score"] for d in r["datatypeScores"]},
            tractability=tract, has_approved_drug=_has_approved_drug(tract),
        ))
    return out


def target_safety(client: HttpClient, target_id: str) -> list[SafetyFlag]:
    t = graphql(client, SAFETY_QUERY, {"id": target_id})["target"]
    flags: list[SafetyFlag] = []
    for liab in t.get("safetyLiabilities") or []:
        tissues = ", ".join(b["tissueLabel"] for b in liab.get("biosamples") or [] if b.get("tissueLabel"))
        flags.append(SafetyFlag("liability", f"{liab['event']} ({tissues})" if tissues else liab["event"]))
    for row in (t.get("baselineExpression") or {}).get("rows") or []:
        tissue = row.get("tissueBiosampleFromSource") or ""
        median = row.get("median")
        if row.get("datasourceId") != "gtex" or median is None:
            continue
        if any(k in tissue.lower() for k in SAFETY_TISSUES) and median >= EXPRESSION_TPM_THRESHOLD:
            flags.append(SafetyFlag("expression", f"{tissue}: {median:.0f} TPM"))
    return flags
