"""Versioned inventory integrity, explicit maintenance and offline lookup."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from descriptors.organisms import (RESOURCE, OrganismInventoryError, default_inventory,
    inventory_identity, load_inventory, resolve_organism)


def document():
    return json.loads(RESOURCE.read_bytes())


@pytest.mark.parametrize('query,expected',[
    ('homo_sapiens','homo_sapiens'),(' HoMo   SaPiEnS ','homo_sapiens'),('h_sapiens','homo_sapiens'),
    ('rat','rattus_norvegicus'),('C57BL/6NJ','mus_musculus_c57bl6nj'),
    ('Mus musculus c57bl6nj','mus_musculus_c57bl6nj'),('129S1/SvImJ','mus_musculus_129s1svimj'),
    ('pig','sus_scrofa'),('berkshire','sus_scrofa_berkshire')])
def test_canonical_scientific_curated_and_strain_identities(query,expected):
    result=resolve_organism(query)
    assert result.status=='resolved' and result.canonical==expected
    assert result.inventory_sha256==hashlib.sha256(RESOURCE.read_bytes()).hexdigest()


@pytest.mark.parametrize('value',[None,'',' N/A ','NA','<NA>','nan',float('nan')])
def test_missing_values_are_not_lookup_failures(value):
    result=resolve_organism(value)
    assert result.status=='missing' and result.canonical is None


@pytest.mark.parametrize('value',['reference','Chinese hamster','hybrid cattle'])
def test_ambiguous_annotations_never_choose_a_species(value):
    result=resolve_organism(value)
    assert result.status=='ambiguous' and len(result.candidates)>1 and result.canonical is None
    assert result.inventory_sha256 in result.diagnostic(value)


def test_fuzzy_hits_are_reproducible_suggestions():
    result=resolve_organism('Homo sapens')
    assert result.status=='unresolved' and result.canonical is None
    assert result.suggestions[0]=='homo_sapiens'
    assert resolve_organism('Homo sapens')==result


@pytest.mark.parametrize('damage',['schema','version','empty','alias_type','undeclared_conflict','wrong_ambiguity','curated_target','canonical_collision'])
def test_malformed_inventory_is_rejected(tmp_path,damage):
    data=document()
    if damage=='schema':data['schema_version']=2
    elif damage=='version':data['inventory_version']=''
    elif damage=='empty':data['species']={}
    elif damage=='alias_type':data['species']['homo_sapiens']='human'
    elif damage=='undeclared_conflict':data['species']['mus_musculus'].append('human')
    elif damage=='wrong_ambiguity':data['ambiguous_aliases']['reference']=['homo_sapiens']
    elif damage=='curated_target':data['curated_aliases']['mouse']='homo_sapiens'
    else:data['species']['homo__sapiens']=[]
    path=tmp_path/'bad.json';path.write_text(json.dumps(data))
    with pytest.raises(OrganismInventoryError):load_inventory(path)


@pytest.mark.parametrize('content',[None,b'{bad json',b'{"schema_version":1,"schema_version":2}',b'\xff'])
def test_missing_corrupt_and_duplicate_resources_fail_clearly(tmp_path,content):
    path=tmp_path/'required.json'
    if content is not None:path.write_bytes(content)
    with pytest.raises(OrganismInventoryError):load_inventory(path)


def test_default_missing_resource_has_no_refresh_or_fallback(tmp_path,monkeypatch):
    import descriptors.organisms as organisms
    default_inventory.cache_clear()
    monkeypatch.setattr(organisms,'RESOURCE',tmp_path/'missing.json')
    try:
        with pytest.raises(OrganismInventoryError,match='required organism inventory'):
            resolve_organism('Human')
        assert not list(tmp_path.iterdir())
    finally:default_inventory.cache_clear()


def test_legacy_names_and_aliases_are_retained():
    # The historical pickle remains an immutable compatibility artifact, not a runtime fallback.
    import pickle
    legacy=RESOURCE.with_name('ens_org.pkl')
    historical=pickle.loads(legacy.read_bytes())
    data=document()
    assert set(historical)==set(data['species'])
    assert all(set(values)==set(data['species'][key]) for key,values in historical.items())
    assert data['provenance']['legacy_resource_sha256']==hashlib.sha256(legacy.read_bytes()).hexdigest()
    assert data['provenance']['upstream_release'] is None


def test_identity_is_detached_from_callers():
    identity=inventory_identity();original=copy.deepcopy(identity)
    identity['provenance']['source_description']='changed by caller'
    assert inventory_identity()==original


def test_public_compatibility_mapping_and_matching_arguments():
    import inspect
    from descriptors import fuzzmatch_organism
    from descriptors.fuzzmatch import ORG_DB
    assert str(inspect.signature(fuzzmatch_organism)) == '(query, min_score=80, min_letters=4)'
    assert fuzzmatch_organism('Human', min_score=101, min_letters=100) == 'homo_sapiens'
    assert fuzzmatch_organism('Homo sapens', min_score=0, min_letters=0) is None
    assert resolve_organism('Homo sapens', min_score=101).suggestions == ()
    before = ORG_DB['homo_sapiens']
    copied = ORG_DB.copy()
    copied['homo_sapiens'].append('unrecorded alias')
    ORG_DB['homo_sapiens'].append('another unrecorded alias')
    assert ORG_DB['homo_sapiens'] == before
    with pytest.raises(TypeError):
        ORG_DB['homo_sapiens'] = []


def test_explicit_local_inventory_uses_selected_bytes_without_changing_default(tmp_path):
    data = document()
    data['inventory_version'] = 'synthetic-local-v1'
    data['species']['homo_sapiens'].append('synthetic local human')
    path = tmp_path / 'local.json'
    path.write_text(json.dumps(data))
    selected = load_inventory(path)
    result = resolve_organism('synthetic local human', inventory=selected)
    assert result.canonical == 'homo_sapiens'
    assert result.inventory_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result.inventory_sha256 != inventory_identity()['sha256']
    assert resolve_organism('synthetic local human').status == 'unresolved'


def test_explicit_maintenance_build_validate_reproduce_and_refuse_replacement(tmp_path):
    source=tmp_path/'supplied.json';source.write_bytes(RESOURCE.read_bytes())
    first,second=tmp_path/'candidate-a.json',tmp_path/'candidate-b.json'
    command=[sys.executable,'-m','descriptors.inventory']
    for output in (first,second):
        result=subprocess.run([*command,'build',str(source),str(output),'--version','synthetic-v1',
                               '--source-description','Supplied local reviewed inventory'],cwd=tmp_path,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        identity=json.loads(result.stdout)
        assert identity['sha256']==hashlib.sha256(output.read_bytes()).hexdigest()
        assert identity['provenance']['input_sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
    assert first.read_bytes()==second.read_bytes()
    result=subprocess.run([*command,'validate',str(first)],cwd=tmp_path,capture_output=True,text=True)
    assert result.returncode==0 and json.loads(result.stdout)['inventory_version']=='synthetic-v1'
    before=first.read_bytes()
    result=subprocess.run([*command,'build',str(source),str(first),'--version','synthetic-v2','--source-description','local'],cwd=tmp_path,capture_output=True,text=True)
    assert result.returncode==2 and first.read_bytes()==before


def test_import_and_lookup_in_child_with_empty_cache_do_not_write(tmp_path):
    import os
    cache=tmp_path/'empty-cache';cache.mkdir()
    env=dict(os.environ,XDG_CACHE_HOME=str(cache))
    code="import sys; assert sys._gcf_offline_guard; import descriptors; from descriptors.organisms import inventory_identity; assert descriptors.fuzzmatch_organism('Human')=='homo_sapiens'; print(inventory_identity()['sha256'])"
    before=RESOURCE.read_bytes()
    result=subprocess.run([sys.executable,'-c',code],cwd=tmp_path,env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()==hashlib.sha256(before).hexdigest()
    assert RESOURCE.read_bytes()==before and not list(cache.rglob('*'))
