import numpy as np
import pytest
from model_quality_lab.monitoring import js_distance

@pytest.mark.parametrize('scenario,expected',[('healthy','PASS'),('feature_skew','FAIL'),('score_shift','PASS'),('regression','FAIL'),('missing_feature','FAIL'),('delayed_labels','INSUFFICIENT_EVIDENCE'),('sparse_slice','INSUFFICIENT_EVIDENCE')])
def test_end_to_end_scenarios(lab,scenario,expected):
    r=lab.run(scenario,bootstrap=400)
    assert r['gate']['decision']==expected
    assert r['pipeline']['processed']
    assert r['trace_id']!='0'*32
    if scenario=='score_shift':
        assert r['gate']['overall']['delta']==0
        assert r['monitoring']['scores']['js_divergence']>.1
    if scenario=='feature_skew':
        assert r['gate']['overall']['delta']<-.1 and r['monitoring']['skew_rate']>.4

def test_late_labels_change_coverage_and_gate(lab):
    r=lab.run('delayed_labels',bootstrap=400)
    assert r['gate']['label_coverage']==.35
    updated=lab.release_labels(r['id'])
    assert updated['gate']['label_coverage']==1 and updated['gate']['decision']=='PASS'
    assert updated['initial_gate']['decision']=='INSUFFICIENT_EVIDENCE'
    # Releasing an identical batch twice is idempotent.
    assert lab.release_labels(r['id'])['gate']==updated['gate']

def test_drift_fixed_reference_bins_detect_distribution_change():
    assert js_distance(np.ones(100),np.ones(100))['js_divergence']==pytest.approx(0)
    assert js_distance(np.ones(100),np.zeros(100))['js_divergence']>.6
    assert js_distance(np.array([np.nan]),np.ones(2))['js_divergence'] is None
