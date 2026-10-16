from copy import deepcopy
import numpy as np
import pytest
from model_quality_lab.data import FeatureBuilder,load_mind
from model_quality_lab.models import RankingModels
from model_quality_lab.schema import ModelSpec

def test_eval_labels_do_not_change_features_or_predictions(dataset,lab):
    changed=deepcopy(dataset)
    for i in changed.test:i.labels=[1-v for v in i.labels]
    np.testing.assert_equal(FeatureBuilder(changed).build(changed.test[0]),lab.models.features.build(dataset.test[0]))
    assert changed.manifest()['fingerprint']!=dataset.manifest()['fingerprint']

def test_temporal_and_identity_leakage_rejected(dataset):
    changed=deepcopy(dataset);changed.test[0].time=changed.train[0].time
    with pytest.raises(ValueError,match='Temporal leakage'):changed.validate()
    changed=deepcopy(dataset);changed.test[0].id=changed.train[0].id
    with pytest.raises(ValueError,match='multiple splits'):changed.validate()

def test_semantic_decoder_outputs_only_offered_unique_items(lab):
    for imp in lab.ds.test[:25]:
        assert set(lab.models.generative.decode(imp))==set(imp.candidates)
        assert len(lab.models.generative.decode(imp))==len(imp.candidates)
        assert lab.models.generative.code(imp.candidates[0])[-1]==imp.candidates[0]

def test_unknown_model_rejected(lab):
    with pytest.raises(ValueError):lab.models.predict(lab.models.features.build(lab.ds.test[0]),'user-supplied-cardinality')

def test_onboarding_schema_enforces_feature_order():
    with pytest.raises(ValueError):ModelSpec(name='test',owner='team',task='ranking',features=['invalid'])

def test_mind_tsv_keeps_impressions_and_temporal_split(tmp_path):
    train=tmp_path/'train';dev=tmp_path/'dev';train.mkdir();dev.mkdir()
    for root in [train,dev]:(root/'news.tsv').write_text('N1\tsports\trunning\tTrail running\nN2\tscience\tspace\tA new star\n')
    rows=[f'{n}\tU{n%12}\t11/10/2019 {1+n//60:02d}:{n%60:02d}:00 AM\tN1\tN1-1 N2-0' for n in range(120)]
    (train/'behaviors.tsv').write_text('\n'.join(rows))
    (dev/'behaviors.tsv').write_text('200\tU1\t11/15/2019 01:00:00 AM\tN1\tN1-0 N2-1\n')
    ds=load_mind(train,dev)
    assert ds.test[0].labels==[0,1]
    assert len(ds.train)==96 and len(ds.validation)==24 and len(ds.test)==1
    assert ds.train[0].user!='U0'

def test_mind_unlabeled_file_is_not_silently_negative(tmp_path):
    train=tmp_path/'train';dev=tmp_path/'dev';train.mkdir();dev.mkdir()
    for root in [train,dev]:
        (root/'news.tsv').write_text('N1\tsports\trunning\tRunning\n')
        (root/'behaviors.tsv').write_text('1\tU1\t11/10/2019 01:00:00 AM\t\tN1\n')
    with pytest.raises(ValueError,match='labeled'):load_mind(train,dev)
