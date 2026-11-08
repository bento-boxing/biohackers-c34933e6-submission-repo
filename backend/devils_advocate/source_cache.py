"""SQLite cache of schema-checked public responses, never model output/secrets."""
import hashlib,json,re,sqlite3,time
from pathlib import Path
from urllib.parse import urlsplit

def source_name(url: str) -> str:
    p=urlsplit(url)
    if p.hostname=='clinicaltrials.gov':return 'ClinicalTrials.gov'
    if p.hostname=='rest.ensembl.org':return 'Ensembl'
    if '/chembl/' in p.path:return 'ChEMBL'
    if 'europepmc' in p.path:return 'Europe PMC'
    if '/ols4/' in p.path:return 'OLS'
    if p.hostname=='api.fda.gov':return 'openFDA'
    if p.hostname=='api.platform.opentargets.org':return 'Open Targets'
    return 'Public API'

def expiration(url: str) -> int:
    p=urlsplit(url)
    if source_name(url)=='ChEMBL':return 86400 if 'drug_indication' in p.path else 7*86400
    if source_name(url)=='ClinicalTrials.gov':return 6*3600 if re.search(r'/NCT\d+$',p.path) else 3600
    if source_name(url)=='Europe PMC':return 6*3600
    if source_name(url)=='Ensembl':return 7*86400
    return 86400

def _verified_response(url: str,data: dict) -> bool:
    """Structural/identity verification, not scientific entailment or completeness.

    Valid bounded search pages retain next-page/limit metadata. They never assert
    that a whole search was exhaustive. Malformed/error bodies are not cached.
    """
    if not isinstance(data,dict) or data.get('errors') or data.get('error'):return False
    source=source_name(url);path=urlsplit(url).path
    if source=='Ensembl':
        requested=re.search(r'/lookup/id/(ENSG\d{11})$',path)
        return bool(re.fullmatch(r'ENSG\d{11}',data.get('id','')) and data.get('species')=='homo_sapiens' and data.get('display_name')
            and (not requested or data['id']==requested[1]))
    if source=='ClinicalTrials.gov':
        nct=re.search(r'/studies/(NCT\d{8})$',path)
        if nct:
            protocol=data.get('protocolSection') or {}
            return protocol.get('identificationModule',{}).get('nctId')==nct[1] and isinstance(protocol.get('statusModule'),dict)
        return (isinstance(data.get('studies'),list)
                and not (data.get('totalCount',0)>0 and not data['studies'])
                and all(isinstance(r,dict) and isinstance(r.get('protocolSection'),dict) for r in data['studies']))
    if source=='Europe PMC':
        rows=data.get('resultList',{}).get('result')
        return (isinstance(rows,list) and not (data.get('hitCount',0)>0 and not rows)
                and all(isinstance(r,dict) and r.get('id') and r.get('source') for r in rows))
    if source=='ChEMBL':
        target=re.search(r'/target/(CHEMBL\d+)\.json$',path)
        molecule=re.search(r'/molecule/(CHEMBL\d+)\.json$',path)
        if target:return data.get('target_chembl_id')==target[1] and isinstance(data.get('target_components'),list)
        if molecule:return data.get('molecule_chembl_id')==molecule[1]
        for segment,key in [('mechanism','mechanisms'),('drug_indication','drug_indications'),('molecule','molecules'),('target/search','targets')]:
            if '/'+segment in path:return isinstance(data.get(key),list)
        return False
    if source=='OLS':return isinstance(data.get('_embedded',{}).get('terms'),list)
    if source=='openFDA':return isinstance(data.get('results'),list)
    if source=='Open Targets':return isinstance(data.get('data'),dict) and not data.get('errors')
    return False  # Only explicitly known public datasets may persist.

def verified_response(url: str,data: dict) -> bool:
    try:return bool(_verified_response(url,data))
    except (AttributeError,TypeError,ValueError):return False

class SourceCache:
    def __init__(self,path: Path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS public_responses
                (key TEXT PRIMARY KEY,source TEXT,url TEXT,scope TEXT,request TEXT,
                 fetched REAL,expires REAL,sha256 TEXT,payload TEXT)''')
            if 'origin' not in {row[1] for row in db.execute('PRAGMA table_info(public_responses)')}:
                db.execute('ALTER TABLE public_responses ADD COLUMN origin TEXT')

    def connect(self):return sqlite3.connect(self.path,timeout=10)

    @staticmethod
    def key(method,url,request,scope):
        scope={k:v for k,v in scope.items() if v is not None and k not in {'disease_aliases','target_aliases','protein_gene_symbols'}}
        raw=json.dumps({'version':1,'method':method,'source':source_name(url),'url':url,'request':request,'scope':scope},sort_keys=True,separators=(',',':'))
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self,key,url):
        with self.connect() as db:row=db.execute('SELECT fetched,expires,sha256,payload,origin FROM public_responses WHERE key=?',(key,)).fetchone()
        if not row or row[1]<=time.time():return None
        try:
            if hashlib.sha256(row[3].encode()).hexdigest()!=row[2]:return None
            data=json.loads(row[3])
            if not verified_response(url,data):return None
            return data,{'fetched_at':row[0],'expires_at':row[1],'sha256':row[2],'origin':row[4] or url}
        except (ValueError,TypeError):return None

    def put(self,key,url,request,scope,data,*,origin=None):
        if not verified_response(url,data):return None
        payload=json.dumps(data,ensure_ascii=False,separators=(',',':'));now=time.time()
        metadata={'fetched_at':now,'expires_at':now+expiration(url),'sha256':hashlib.sha256(payload.encode()).hexdigest(),'origin':origin or url}
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO public_responses VALUES (?,?,?,?,?,?,?,?,?,?)',
                (key,source_name(url),url,json.dumps(scope,sort_keys=True),json.dumps(request,sort_keys=True),now,metadata['expires_at'],metadata['sha256'],payload,metadata['origin']))
        return metadata
