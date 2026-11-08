"""Live identity-only checks through the application resolver; no paid AI."""
import json
from pathlib import Path
from .http_client import JsonClient, RetrievalError
from .models import TargetInput
from .trial_retriever import TargetIdentityError, resolve_target

def main():
    client=JsonClient()
    rows=[]
    for symbol,identifier,accession in [('BACE1','CHEMBL4822','P56817'),('LRRK2','CHEMBL1075104','Q5S007'),
                                        ('EGFR','CHEMBL203','P00533'),('FAKEGENE123',None,None)]:
        try:
            target=TargetInput(disease_name='Identity diagnostic only',target_symbol=symbol,chembl_target_id=identifier,uniprot=accession)
            result=resolve_target(client,target)
            row={'symbol':symbol,'supplied_id':identifier,'resolved_id':result,'status':'resolved' if result else 'unknown'}
            if result:row['cached_recheck']=resolve_target(client,target)==result
        except TargetIdentityError:
            row={'symbol':symbol,'supplied_id':identifier,'status':'identity_rejected'}
        except RetrievalError as exc:
            row={'symbol':symbol,'supplied_id':identifier,'status':'temporarily_unavailable','http_status':exc.status_code}
        rows.append(row);print(json.dumps(row),flush=True)
    (Path(__file__).parent/'validation/chembl_identity_report.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')

if __name__=='__main__':main()
