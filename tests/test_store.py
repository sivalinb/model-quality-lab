from concurrent.futures import ThreadPoolExecutor
import pytest
from model_quality_lab.store import Store

BODY={'model':'candidate','user':'0'*20,'cohort':'new','candidate_ids':['a','b'],'scores':[.9,.1],'event_time':1}

def test_duplicate_envelope_and_conflicting_identity(tmp_path):
    s=Store(tmp_path/'events.db')
    assert s.accept('e','prediction','r',BODY)
    assert not s.accept('e','prediction','r',BODY)
    with pytest.raises(ValueError):s.accept('e','prediction','r',{**BODY,'scores':[.1,.9]})
    s.drain_batch();assert s.stats()['predictions']==1

def test_labels_arrive_before_predictions(tmp_path):
    s=Store(tmp_path/'events.db')
    s.accept('l','label','r',{'candidate_ids':['a','b'],'clicked_ids':['b']})
    s.drain_batch();assert s.joined()==[]
    s.accept('p','prediction','r',BODY);s.drain_batch()
    assert s.joined()[0]['label']['clicked_ids']==['b']

def test_fenced_worker_cannot_commit_after_reclaim(tmp_path):
    s=Store(tmp_path/'events.db');s.accept('e','prediction','r',BODY)
    old=s.claim(0);new=s.claim(30)
    with pytest.raises(ValueError,match='Expired'):s.complete(old)
    s.complete(new);assert s.stats()['predictions']==1

def test_poison_event_does_not_block_valid_events(tmp_path):
    s=Store(tmp_path/'events.db');s.accept('bad','prediction','r',{})
    s.accept('good','prediction','r2',BODY);s.drain_batch()
    assert s.stats()['dead_letters']==1 and s.stats()['predictions']==1 and s.stats()['pending']==0

def test_concurrent_consumers_never_duplicate_projections(tmp_path):
    path=tmp_path/'events.db';s=Store(path)
    s.accept_many([(f'e{n}','prediction',f'r{n}',BODY) for n in range(40)])
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda _: Store(path).drain(),range(3)))
    assert s.stats()['predictions']==40 and s.stats()['pending']==0

def test_bulk_accept_rolls_back_on_identity_conflict(tmp_path):
    s=Store(tmp_path/'events.db');s.accept('old','prediction','r',BODY)
    with pytest.raises(ValueError):s.accept_many([('new','prediction','r2',BODY),('old','prediction','r',{})])
    assert s.stats()['inbox']==1
