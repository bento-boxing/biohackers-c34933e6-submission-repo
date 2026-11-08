"""Resolve audit inputs with public Ensembl/OLS, no model requests."""
import json,time,sys,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from devils_advocate.http_client import JsonClient,RetrievalError

OUT=Path('devils_advocate/validation/cross_disease'); OUT.mkdir(parents=True,exist_ok=True)
CASES=[('CCR5','HIV infection','CCR5'),('PCSK9','Hypercholesterolemia','PCSK9'),
 ('EGFR','EGFR-mutant non-small-cell lung cancer','EGFR'),('BACE1',"Alzheimer's disease",'BACE1'),
 ('LRRK2',"Parkinson's disease",'LRRK2'),('BCL2','scoliosis','BCL2'),
 ('preclinical','Rett syndrome','SLC12A5'),('unsupported','achondroplasia','CCR5'),
 ('fabricated','HIV infection','AUDIT_FAKE_GENE_ZXQ987'),('invalid_disease','HIV infection','CCR5'),
 ('GLP1R','Type 2 diabetes mellitus','GLP1R'),('CFTR','cystic fibrosis','CFTR'),
 ('SMN2','spinal muscular atrophy','SMN2'),('rare','NGLY1 deficiency','NGLY1')]

def review_identifiers():
    rows=json.loads((OUT/'references.json').read_text())
    canonical={'CCR5':'HIV infectious disease','fabricated':'HIV infectious disease',
        'invalid_disease':'HIV infectious disease','EGFR':'non-small cell lung carcinoma'}
    norm=lambda s:re.sub(r'[^a-z0-9]','',s.lower().replace("'s",''))
    c=JsonClient()
    for row in rows:
        candidates=row.get('disease_candidates',[])
        exact=[d for d in candidates if norm(d['label'])==norm(canonical.get(row['case'],row['target_input']['disease_name'])) and d['id'].startswith('MONDO:')]
        if row['case']=='BACE1':
            data=c.get('https://www.ebi.ac.uk/ols4/api/ontologies/mondo/terms',{'obo_id':'MONDO:0004975'})
            exact=[{'id':r['obo_id'],'label':r['label'],'iri':r.get('iri')} for r in data.get('_embedded',{}).get('terms',[]) if r.get('obo_id')=='MONDO:0004975' and norm(r['label'])=='alzheimerdisease']
        if len(exact)==1:
            row['disease']=exact[0]
            if row['case']!='invalid_disease':row['target_input']['disease_id']=exact[0]['id'].replace(':','_')
        if row['case']=='PCSK9':row['phenotype_reference']=[d for d in candidates if d['id']=='HP:0003124'];row['note']='Hypercholesterolemia is a phenotype; no narrower familial disease identifier was assigned.'
    c.close();(OUT/'references.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    print(json.dumps([{'case':r['case'],'target_input':r['target_input']} for r in rows]))

if __name__=='__main__' and '--review-identifiers' in sys.argv:
    review_identifiers();sys.exit(0)

if __name__=='__main__':
    c=JsonClient(cache_path=Path('devils_advocate/runtime/cross-disease-references.sqlite3'))
    references=[]
    for key,disease,symbol in CASES:
        row={'case':key,'target_input':{'disease_name':disease,'target_symbol':symbol},'gene':None,'disease':None,'errors':[]}
        if key!='fabricated':
            try:
                gene=c.get('https://rest.ensembl.org/lookup/symbol/homo_sapiens/'+symbol,{'content-type':'application/json'})
                if gene.get('species')=='homo_sapiens' and gene.get('display_name')==symbol:
                    row['gene']={k:gene.get(k) for k in ['id','display_name','species','description','biotype']}
                    row['target_input']['target_id']=gene['id']
                else:row['errors'].append('Ensembl exact human symbol unresolved')
            except RetrievalError:row['errors'].append('Ensembl unavailable')
        # The molecular subtype is retained in disease_name; ontology lookup
        # validates its broader disease entity rather than inventing a subtype ID.
        query='non-small cell lung carcinoma' if key=='EGFR' else disease
        try:
            raw=c.get('https://www.ebi.ac.uk/ols4/api/search',{'q':query,'ontology':'mondo','type':'class','exact':'true','rows':5})
            docs=raw.get('response',{}).get('docs',[])
            row['disease_candidates']=[{'id':r.get('obo_id'),'label':r.get('label'),'iri':r.get('iri')} for r in docs]
            if len(docs)==1 and docs[0].get('obo_id'):
                row['disease']=row['disease_candidates'][0]
                row['target_input']['disease_id']=docs[0]['obo_id'].replace(':','_')
        except RetrievalError:row['errors'].append('OLS unavailable; lexical input explicitly retained')
        if key=='invalid_disease':row['target_input']['disease_id']='MONDO_999999999';row['note']='Intentional nonexistent ID, not a verified identifier.'
        references.append(row);(OUT/'references.json').write_text(json.dumps(references,indent=2),encoding='utf-8')
        print(json.dumps(row),flush=True)
    c.close()
