import pytest
from model_quality_lab.data import synthetic
from model_quality_lab.engine import Lab

@pytest.fixture(scope='session')
def dataset(): return synthetic()

@pytest.fixture(scope='session')
def lab(tmp_path_factory,dataset): return Lab(tmp_path_factory.mktemp('lab'),dataset)
