"""Independent reference checks; never inject expected papers into a tested job."""
import json,sys,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from devils_advocate.http_client import JsonClient
ROOT=Path('devils_advocate/validation/cross_disease')
EXPECTED={'CCR5':['18832244','20151839'],'PCSK9':['28304224','30403574'],
 'EGFR':['29151359'],'BACE1':['29719179','30970186'],'LRRK2':['35675433'],
 'BCL2':['31337422'],'preclinical':['26733678','31366578'],
 'GLP1R':['27295427'],'CFTR':['22047557','31697873'],'SMN2':['29091570'],
 'rare':['24651605','25605922']}

if __name__=='__main__':
 c=JsonClient();ids=sorted({p for group in EXPECTED.values() for p in group})
 data=c.get('https://www.ebi.ac.uk/europepmc/webservices/rest/search',{'query':'SRC:MED AND ('+' OR '.join('EXT_ID:'+p for p in ids)+')','resultType':'core','format':'json','pageSize':40})
 (ROOT/'landmarks_sources.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 records={r['id']:r for r in data.get('resultList',{}).get('result',[])}
 summary={'method':'Independent PMID lookup, not supplied to tested retrieval or Gemini; title/abstract verified against Europe PMC MED source records.',
  'cases':{name:[{'id':'MED:'+p,'url':'https://pubmed.ncbi.nlm.nih.gov/'+p+'/',
    'found':p in records,'title':records.get(p,{}).get('title'),'doi':records.get(p,{}).get('doi')} for p in group] for name,group in EXPECTED.items()}}
 (ROOT/'landmarks.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
 for p,r in records.items():
  abstract=re.sub('<[^>]+>',' ',r.get('abstractText',''));conclusion=re.split(r'Conclusions?\s*:?|Interpretation\s*:',abstract,flags=re.I)[-1]
  print(json.dumps({'pmid':p,'title':r['title'],'conclusion':conclusion[-1050:]}))
 c.close()
