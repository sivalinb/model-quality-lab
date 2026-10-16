import pytest
from fastapi.testclient import TestClient
from model_quality_lab.api import create_app

@pytest.fixture(scope='module')
def client(tmp_path_factory,dataset):
    return TestClient(create_app(tmp_path_factory.mktemp('api'),dataset))

def test_health_and_real_prediction(client):
    assert client.get('/healthz').status_code==200
    r=client.post('/api/predict',json={'index':0,'model':'candidate'}).json()
    assert len(r['scores'])==12 and r['latency_ms']>0
    assert r['trace_id']!='0'*32
    assert client.post('/api/worker/drain',json={}).json()['projected']>=1

def test_invalid_config_and_cross_origin_writes_rejected(client):
    assert client.post('/api/experiments',json={'scenario':'unknown'}).status_code==422
    assert client.post('/api/experiments',json={'scenario':'healthy'},headers={'Origin':'https://unrelated.example'}).status_code==403

def test_raw_text_and_unbounded_model_names_are_not_stored(client):
    before=client.get('/api/state').json()['pipeline']['inbox']
    body={'event_id':'test','request_id':'test','kind':'prediction','body':{'model':'arbitrary-model','raw_prompt':'do not capture me'}}
    assert client.post('/api/events',json=body).status_code==422
    assert client.get('/api/state').json()['pipeline']['inbox']==before

def test_event_acceptance_is_distinct_from_projection(client):
    body={'event_id':'event-1','request_id':'request-1','kind':'label','body':{'candidate_ids':['a'],'clicked_ids':['a']}}
    assert client.post('/api/events',json=body).json()=={'accepted':True,'projected':False,'event_id':'event-1'}
    assert client.post('/api/events',json=body).json()['accepted'] is False
    assert client.post('/api/worker/drain',json={}).status_code==200

def test_metrics_have_bounded_labels(client):
    m=client.get('/metrics').text
    assert 'mql_inference_seconds' in m
    assert 'request_id=' not in m and 'user=' not in m

def test_ui_and_requirement_map_are_available(client):
    assert 'Model Quality Lab' in client.get('/').text
    assert len(client.get('/api/requirements').json())>=12
    assert client.get('/static/app.js').status_code==200
