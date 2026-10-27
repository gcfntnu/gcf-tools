"""Authoritative complete catalogue and one-library expanded-row regressions."""

import copy
import json
from importlib.resources import files

import pytest

from configmaker.indexes import (IndexNormalizationError, catalogue_identity, load_catalogue,
                                 normalize_indexes, normalize_rows, reverse_complement)
from configmaker.project_pairs import validate_project_pairs
from configmaker.validation import validate_inputs
from test_validation import customer_row, sample_sheet, submission_form

PROJECT = 'GCF-2099-001'


def test_catalogue_resources_complete_and_identified_offline():
    catalogue = load_catalogue()
    assert len(catalogue['entries']) == 192
    for family in ('GA', 'TT'):
        assert {'SI-{}-{}{}'.format(family, letter, number) for letter in 'ABCDEFGH' for number in range(1, 13)} <= set(catalogue['entries'])
    assert len(catalogue_identity()['sha256']) == 64
    assert json.loads(files('configmaker').joinpath('tenx_indexes.json').read_bytes())['sources']
    for name, entry in catalogue['entries'].items():
        normalized = normalize_indexes(name)
        assert len(normalized) == (4 if entry['kind'] == 'single' else 1)
        assert len({tuple(row.items()) for row in normalized}) == len(normalized)


def test_vendor_examples_and_explicit_orientation_do_not_change_literal_inputs():
    assert normalize_indexes('SI-GA-A1') == [dict(index=i, index2='') for i in ('GGTTTACT', 'CTAAACGG', 'TCGGCGTC', 'AACCGTAA')]
    assert normalize_indexes('SI-TT-A1') == [dict(index='GTAACATGCG', index2='AGTGTTACCT')]
    assert normalize_indexes('SI-TT-A1', i5_orientation='reverse-complement') == [dict(index='GTAACATGCG', index2='AGGTAACACT')]
    assert normalize_indexes('gtaacatgcg', 'AGGTAACACT', i5_orientation='reverse-complement') == [dict(index='GTAACATGCG', index2='AGGTAACACT')]


@pytest.mark.parametrize('index,index2,orientation,code', [
    ('SI-UNKNOWN-A1', '', 'forward', 'index.unknown_name'),
    ('SI-TT-A1', 'SI-TT-A2', 'forward', 'index.conflicting_pair'),
    ('SI-GA-A1', 'ACGT', 'forward', 'index.conflicting_pair'),
    ('ACGT', 'SI-TT-A1', 'forward', 'index.incomplete_pair'),
    ('AC GT', '', 'forward', 'index.invalid_sequence'),
    ('ACGT', '', 'automatic', 'index.orientation'),
])
def test_actionable_normalization_failures(index, index2, orientation, code):
    with pytest.raises(IndexNormalizationError) as caught:
        normalize_indexes(index, index2, i5_orientation=orientation)
    assert caught.value.code == code


def test_expansion_preserves_source_library_and_metadata_without_mutation():
    rows = [dict(Sample_ID='library-01', Sample_Project=PROJECT, Lane='1', index='SI-GA-A1', _row=8, OverrideCycles='Y28;I8;Y90')]
    before = copy.deepcopy(rows)
    result = normalize_rows(rows)
    assert rows == before
    assert len(result) == 4
    assert {row['Sample_ID'] for row in result} == {'library-01'}
    assert all(row['_row'] == 8 and row['_index_provenance']['original_index'] == 'SI-GA-A1' for row in result)
    assert {row['_index_provenance']['oligo'] for row in result} == {1, 2, 3, 4}


def test_explicit_expanded_rows_require_one_form_row_and_reject_duplicate_assignment(tmp_path):
    rows = [['library-01', PROJECT, item['index']] for item in normalize_indexes('SI-GA-A1')]
    sheet = sample_sheet(tmp_path / 'SampleSheet.csv', rows, ['Sample_ID', 'Sample_Project', 'index'])
    form = submission_form(tmp_path / 'form.xlsx', [customer_row('library-01', project=PROJECT)])
    result = validate_inputs([sheet], [form])
    assert result.ok, result.render_text()
    assert result.summary['planned_sample_count'] == 1
    assert len(result.samples) == 1
    sheet = sample_sheet(sheet, rows + [rows[0]], ['Sample_ID', 'Sample_Project', 'index'])
    result = validate_inputs([sheet], [form])
    assert not result.ok
    assert 'sample.duplicate_definition' in {item['code'] for item in result.findings}


def test_whole_flowcell_expands_single_library_then_detects_other_library_collision(tmp_path):
    sheets, forms = [], []
    for project, sid, index in [(PROJECT, 'library-01', 'SI-GA-A1'), ('GCF-2099-002', 'library-02', 'SI-GA-A2')]:
        sheets.append(sample_sheet(tmp_path / ('SampleSheet_' + project + '.csv'), [[sid, project, index]], ['Sample_ID', 'Sample_Project', 'index']))
        forms.append(submission_form(tmp_path / (project + '_form.xlsx'), [customer_row(sid, project=project)]))
    result = validate_project_pairs(sheets, forms)
    assert result.ok, result.render_text()
    assert len(result.assignments) == 8
    assert result.summary['planned_sample_count'] == 2
    sheets[1].write_text(sheets[1].read_text().replace('SI-GA-A2', 'GGTTTACT'))
    result = validate_project_pairs(sheets, forms)
    assert not result.ok
    assert 'demux.index_collision' in {item['code'] for item in result.findings}
