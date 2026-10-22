"""Shared resolver compatibility and string-indexed metadata regressions."""
import copy
import pandas as pd
import pytest

from descriptors import fuzzmatch_organism, fuzzmatch_reference, infer_by_descriptor


@pytest.mark.parametrize('query,expected',[('Human','homo_sapiens'),('  HOMO SAPIENS  ','homo_sapiens'),
    ('Mouse','mus_musculus'),('Homo sapens',None),('reference',None),(None,None),('N/A',None),('',None)])
def test_exact_aliases_missing_and_diagnostic_only_fuzzy_matching(query,expected):
    assert fuzzmatch_organism(query)==expected


@pytest.mark.parametrize('index',[['001','001A','CTRL'],[11,12,13]])
def test_descriptor_assignment_is_label_independent_and_lossless(index,caplog):
    unknown='  Unlisted annotation (retain verbatim)!  '
    frame=pd.DataFrame({'Organism':['Human','Mouse',unknown]},index=index)
    output,_=infer_by_descriptor(frame,{'Organism':{'dtype':'string','subtype':'organism'}})
    assert list(output.index)==index
    assert list(output.Organism)==['homo_sapiens','mus_musculus',unknown]
    assert 'unresolved' in caplog.text.lower() and str(index[-1]) in caplog.text


def test_reference_matcher_retains_its_original_return_contract():
    assert fuzzmatch_reference('CTRL')=='CTRL'
