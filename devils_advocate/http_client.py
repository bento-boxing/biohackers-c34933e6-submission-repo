"""Bounded public HTTP, source rate limits, persistent provenance and concurrency."""
import copy,json,time,threading
from email.utils import parsedate_to_datetime
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
import requests
from requests.adapters import HTTPAdapter
from .source_cache import SourceCache,source_name,expiration,verified_response

class RetrievalError(RuntimeError):
    def __init__(self,message: str,*,status_code: int | None=None):
        super().__init__(message);self.status_code=status_code

class RetrievalDeadlineExceeded(RuntimeError):
    pass

class JsonClient:
    def __init__(self,min_interval: float=.35,*,cache_path=None,max_workers: int=1):
        self.session=self._new_session();self._main_thread=threading.get_ident();self._local=threading.local()
        self.cache={};self.persistent_cache=SourceCache(cache_path) if cache_path else None
        self.max_workers=max(1,min(int(max_workers),4));self.min_interval=min_interval;self.last_request=0.
        self._lock=threading.RLock();self._key_locks={};self._host_next={}
        self._observer=None;self._deadline=None;self._should_cancel=None;self._profile=None;self._profile_start=None
        self.scope={};self.refresh=False
        self._executor=None

    @staticmethod
    def _new_session():
        session=requests.Session();session.headers['User-Agent']='Agentverse-Target-Challenger/0.2'
        session.mount('https://',HTTPAdapter(max_retries=0))
        return session

    def _session(self):
        if threading.get_ident()==self._main_thread:return self.session
        if not hasattr(self._local,'session'):self._local.session=self._new_session()
        return self._local.session

    def map(self,function,items):
        if self.max_workers==1:return [function(item) for item in items]
        if self._executor is None:self._executor=ThreadPoolExecutor(max_workers=self.max_workers,thread_name_prefix='public-source')
        futures=[self._executor.submit(function,item) for item in items]
        results=[];failure=None
        for future in futures:
            try:results.append(future.result())
            except Exception as exc:results.append(None);failure=failure or exc
        if failure:raise failure  # Drain workers before the scope/deadline context is restored.
        return results

    def close(self):
        if self._executor:self._executor.shutdown(wait=True)
        self.session.close()

    @contextmanager
    def tracking(self,observer=None,*,budget_seconds=300,should_cancel=None,scope=None,refresh=False):
        previous=(self._observer,self._deadline,self._should_cancel,self._profile,self._profile_start,self.scope,self.refresh)
        started=time.monotonic();self._profile_start=started
        self._observer,self._deadline,self._should_cancel=observer,started+budget_seconds,should_cancel
        self.scope=scope or {};self.refresh=refresh
        self._profile={'started_at':time.time(),'total_seconds':0.,'requests':0,'cache_hits':0,'cache_misses':0,
            'network_attempts':0,'completed_requests':0,'source_seconds':{},'response_provenance':[]}
        profile=self._profile
        try:yield profile
        finally:
            profile['total_seconds']=round(time.monotonic()-started,6)
            self._observer,self._deadline,self._should_cancel,self._profile,self._profile_start,self.scope,self.refresh=previous

    def _check_budget(self):
        if self._should_cancel and self._should_cancel():raise RetrievalDeadlineExceeded('Retrieval stopped after cancellation was observed.')
        if self._deadline is not None and time.monotonic()>=self._deadline:
            raise RetrievalDeadlineExceeded('Biomedical retrieval exceeded its time budget; no model calls were started.')

    def _rate_limit(self,url):
        host=urlsplit(url).hostname
        with self._lock:
            now=time.monotonic();ready=max(now,self._host_next.get(host,0.))
            interval=max(self.min_interval,1.25) if host=='clinicaltrials.gov' else self.min_interval
            self._host_next[host]=ready+interval
        time.sleep(max(0.,ready-now));self._check_budget()

    def _emit(self,url,state,**values):
        with self._lock:
            event={'source':source_name(url),'operation':urlsplit(url).path,'state':state,'at':time.time(),
                'retry_policy_max_attempts':3,**values}
            if self._profile is not None:
                p=self._profile
                if state=='request':p['requests']+=1;p['cache_misses']+=1
                if state=='cache_hit':p['cache_hits']+=1
                if state=='completed':p['completed_requests']+=1
                if state in ['completed','failed']:
                    totals=p['source_seconds'];totals[event['source']]=round(totals.get(event['source'],0.)+values.get('duration_seconds',0.),6)
                if state in ['completed','cache_hit']:
                    p['response_provenance'].append({k:event[k] for k in ['source','operation','state','provenance','fetched_at','expires_at','sha256','origin'] if k in event})
                event['profile']={k:copy.deepcopy(v) for k,v in p.items() if k!='response_provenance'}
                event['profile']['total_seconds']=round(time.monotonic()-self._profile_start,6)
            if self._observer:self._observer(event)

    def get(self,url: str,params: dict | None=None) -> dict:
        return self._request('GET',url,params or {})

    def post_json(self,url: str,payload: dict) -> dict:
        return self._request('POST',url,payload)

    def cached_response(self,url):
        """Lookup for batch planning, without turning a miss into a network call."""
        if self.refresh:return None
        key=SourceCache.key('GET',url,{},self.scope)
        cached=self.cache.get(key)
        if cached and cached[1]['expires_at']>time.time():
            self._emit(url,'cache_hit',provenance='CACHED_MEMORY',**cached[1]);return copy.deepcopy(cached[0])
        cached=self.persistent_cache.get(key,url) if self.persistent_cache else None
        if cached:
            self.cache[key]=cached;self._emit(url,'cache_hit',provenance='CACHED_PERSISTENT',**cached[1]);return copy.deepcopy(cached[0])
        return None

    def prime_verified_record(self,url,data,*,origin):
        if not self.persistent_cache or not verified_response(url,data):return
        key=SourceCache.key('GET',url,{},self.scope)
        metadata=self.persistent_cache.put(key,url,{},self.scope,data,origin=origin)
        if metadata:self.cache[key]=(copy.deepcopy(data),metadata)

    def _request(self,method,url,parameters):
        self._check_budget()
        key=SourceCache.key(method,url,parameters,self.scope)
        with self._lock:guard=self._key_locks.setdefault(key,threading.Lock())
        with guard:
            cached=None if self.refresh else self.cache.get(key)
            if cached and cached[1]['expires_at']>time.time():
                self._emit(url,'cache_hit',provenance='CACHED_MEMORY',**cached[1]);return copy.deepcopy(cached[0])
            if self.persistent_cache and not self.refresh:
                cached=self.persistent_cache.get(key,url)
                if cached:
                    self.cache[key]=cached
                    self._emit(url,'cache_hit',provenance='CACHED_PERSISTENT',**cached[1]);return copy.deepcopy(cached[0])
            started=time.monotonic();self._emit(url,'request',started_at=time.time())
            maximum=3 if method=='GET' else 1
            try:
                for attempt in range(maximum):
                    self._rate_limit(url)
                    with self._lock:
                        if self._profile is not None:self._profile['network_attempts']+=1
                    try:
                        session=self._session()
                        response=session.get(url,params=parameters,timeout=(5,20)) if method=='GET' else session.post(url,json=parameters,timeout=(5,20))
                        if response.status_code in [429,500,502,503,504] and attempt+1<maximum:
                            self._emit(url,'retry',status_code=response.status_code,retries_observed=attempt+1)
                            # Honor short Retry-After; fail rather than retry before a long server-requested wait.
                            retry_after=response.headers.get('Retry-After') if hasattr(response,'headers') else None
                            try:delay=float(retry_after) if retry_after else .5*(2**attempt)
                            except (TypeError,ValueError):
                                try:delay=max(0.,parsedate_to_datetime(retry_after).timestamp()-time.time())
                                except (TypeError,ValueError,OverflowError):delay=.5*(2**attempt)
                            if delay>10:response.raise_for_status()
                            time.sleep(max(0.,delay));continue
                        response.raise_for_status();break
                    except (requests.Timeout,requests.ConnectionError):
                        if attempt+1==maximum:raise
                        self._emit(url,'retry',retries_observed=attempt+1);time.sleep(.5*(2**attempt))
                self._check_budget();data=response.json()
                if not isinstance(data,dict):raise ValueError('Expected a JSON object from the API')
                metadata={'fetched_at':time.time(),'expires_at':time.time()+expiration(url)}
                cacheable=not self.persistent_cache or verified_response(url,data)
                if cacheable:
                    if self.persistent_cache:metadata=self.persistent_cache.put(key,url,parameters,self.scope,data) or metadata
                    self.cache[key]=(copy.deepcopy(data),metadata)
                history=getattr(getattr(getattr(response,'raw',None),'retries',None),'history',None)
                retries=attempt+(len(history) if isinstance(history,(list,tuple)) else 0)
                self._emit(url,'completed',status_code=response.status_code,retries_observed=retries,
                    duration_seconds=round(time.monotonic()-started,6),provenance='LIVE',cacheable=cacheable,**metadata)
                return copy.deepcopy(data)
            except (requests.RequestException,ValueError,RetrievalDeadlineExceeded) as exc:
                response=getattr(exc,'response',None)
                self._emit(url,'failed',status_code=response.status_code if response is not None else None,
                    duration_seconds=round(time.monotonic()-started,6),error_type=type(exc).__name__)
                if isinstance(exc,RetrievalDeadlineExceeded):raise
                raise RetrievalError(f'{url}: {type(exc).__name__}',status_code=response.status_code if response is not None else None) from exc
