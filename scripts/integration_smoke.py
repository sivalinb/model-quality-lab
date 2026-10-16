"""Verify actual HTTP/metrics/traces, optionally the full Kafka and analytics stack."""
import argparse
import json
import time
import urllib.request
from pathlib import Path

def request(url,body=None,headers=None):
    req=urllib.request.Request(url,json.dumps(body).encode() if body is not None else None,{'Content-Type':'application/json',**(headers or {})})
    with urllib.request.urlopen(req,timeout=30) as r:
        raw=r.read().decode()
        try:return json.loads(raw)
        except json.JSONDecodeError:return raw

def wait(fn,timeout=150):
    deadline=time.monotonic()+timeout;last=None
    while time.monotonic()<deadline:
        try:
            value=fn()
            if value:return value
        except Exception as e:last=f'{type(e).__name__}: {str(e)[:300]}'
        time.sleep(1)
    raise AssertionError(f'Timed out waiting for integration evidence; last error class {last}')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--in-process',action='store_true');p.add_argument('--distributed',action='store_true');args=p.parse_args()
    if args.in_process:
        from fastapi.testclient import TestClient
        from model_quality_lab.api import create_app
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            c=TestClient(create_app(Path(d)))
            for scenario,expected in [('healthy','PASS'),('feature_skew','FAIL'),('score_shift','PASS'),('delayed_labels','INSUFFICIENT_EVIDENCE')]:
                r=c.post('/api/experiments',json={'scenario':scenario}).json();assert r['gate']['decision']==expected
                assert r['trace_id']!='0'*32
            assert 'mql_experiments_total' in c.get('/metrics').text
        print('In-process API, gates, metrics and SDK trace integration passed.');return
    base='http://127.0.0.1:7856'
    wait(lambda:request(base+'/healthz'))
    r=request(base+'/api/experiments',{'scenario':'feature_skew'});assert r['gate']['decision']=='FAIL'
    request(base+'/api/experiments',{'scenario':'healthy'})
    predict=request(base+'/api/predict',{'index':0,'model':'candidate'})
    assert predict['latency_ms']>0
    assert 'mql_experiments_total' in request(base+'/metrics')
    assert request(base+'/api/traces')
    if args.distributed:
        before_join=request(base+'/api/state')['pipeline']['joined_predictions']
        outcome_id=predict['request_id']+':outcome'
        event={'event_id':outcome_id,'request_id':predict['request_id'],'kind':'label',
               'body':{'candidate_ids':predict['candidate_ids'],'clicked_ids':predict['candidate_ids'][:1]}}
        assert request(base+'/api/events',event)['transport']=='kafka'
        request(base+'/api/events',event)
        wait(lambda:request(base+'/api/state')['pipeline']['joined_predictions']>before_join)
        import base64
        auth='Basic '+base64.b64encode(b'mql:local-lab').decode()
        def ch():
            q="SELECT count() FROM mql_events FINAL WHERE event_id='"+outcome_id+"'"
            req=urllib.request.Request('http://127.0.0.1:8127',q.encode(),{'Authorization':auth})
            with urllib.request.urlopen(req,timeout=10) as x:return int(x.read())==1
        wait(ch)
        # Query actual scrapes and a provisioned dashboard, rather than health endpoints alone.
        wait(lambda:request('http://127.0.0.1:9096/api/v1/query?query=mql_experiments_total')['data']['result'])
        dashboard=request('http://127.0.0.1:3016/api/dashboards/uid/model-quality-lab')
        assert len(dashboard['dashboard']['panels'])>=8
        # Use Jaeger's documented v3 query contract, rather than its internal UI API.
        wait(lambda:'model-quality-lab' in request('http://127.0.0.1:16696/api/v3/services')['services'])
        wait(lambda:request('http://127.0.0.1:16696/api/v3/traces/'+r['trace_id'])['result']['resourceSpans'])
        print('Distributed path passed: HTTP → Kafka → WAL projection + ClickHouse FINAL; Prometheus, Grafana and OTLP/Jaeger verified.')
    else:print('Live HTTP path passed; native telemetry services can be checked separately.')

if __name__=='__main__':main()
