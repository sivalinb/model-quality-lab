import math
import numpy as np
import pytest
from model_quality_lab.evaluation import ranking_metrics,paired_summary,release_gate

def test_metrics_hand_calculated():
    m=ranking_metrics([0,1,1],[.9,.8,.7],['a','b','c'],k=2)
    assert m['ndcg']==pytest.approx((1/math.log2(3))/(1+1/math.log2(3)))
    assert m['mrr']==.5 and m['recall']==.5

def test_all_negative_excluded_and_ties_deterministic():
    assert ranking_metrics([0,0],[.1,.2],['a','b'])['eligible'] is False
    m=ranking_metrics([1,0],[.5,.5],['z','a'])
    assert m['mrr']==.5

@pytest.mark.parametrize('labels,scores,ids', [([1],[float('nan')],['a']),([1],[.4,.5],['a']),([2],[.4],['a']),([1,0],[.2,.3],['a','a'])])
def test_invalid_metric_inputs(labels,scores,ids):
    with pytest.raises(ValueError):ranking_metrics(labels,scores,ids)

def rows(delta=0):
    return [{'user':f'u{n%80}','cohort':'new' if n%2==0 else 'returning',
             'baseline':{'eligible':True,'ndcg':.7,'mrr':.6,'recall':1},
             'candidate':{'eligible':True,'ndcg':.7+delta,'mrr':.6,'recall':1}} for n in range(240)]

@pytest.mark.parametrize('delta,decision',[(0,'PASS'),(-.2,'FAIL')])
def test_noninferiority_gate(delta,decision):
    assert release_gate(rows(delta),240,bootstrap=400)['decision']==decision

def test_small_sample_and_missing_labels_never_pass():
    assert release_gate(rows()[:10],10)['decision']=='INSUFFICIENT_EVIDENCE'
    assert release_gate(rows(),1000)['decision']=='INSUFFICIENT_EVIDENCE'

def test_user_clustering_prevents_fake_independence():
    r=rows();r=[{**v,'user':'one-user'} for v in r]
    result=release_gate(r,240)
    assert result['overall']['users']==1
    assert result['decision']=='INSUFFICIENT_EVIDENCE'

def test_paired_constant_effect_interval_and_family_correction():
    result=release_gate(rows(-.1),240,bootstrap=400)
    assert result['overall']['ci']==pytest.approx([-.1,-.1])
    assert result['overall']['confidence']==pytest.approx(1-.05/3)

def test_no_quality_labels_has_no_interval():
    assert paired_summary([])['ci'] is None

def test_data_defect_is_an_independent_blocker():
    assert release_gate(rows(),240,skew=.2)['decision']=='FAIL'
