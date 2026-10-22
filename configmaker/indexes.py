"""Offline 10x index normalization, API 1. No files are modified or fetched.

The catalogue stores forward oligo sequences. Callers explicitly select i5
forward or reverse-complement representation for their converter/instrument.
Explicit sequences are already in caller orientation and are never reoriented.
"""

import copy
import hashlib
import json
import re
from importlib.resources import files

INDEX_API_VERSION = 1


class IndexNormalizationError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def reverse_complement(sequence):
    return sequence.translate(str.maketrans('ACGTNacgtn', 'TGCANtgcan'))[::-1]


def load_catalogue():
    content = files('configmaker').joinpath('tenx_indexes.json').read_bytes()
    catalogue = json.loads(content)
    if catalogue.get('schema_version') != 1 or catalogue.get('orientation') != 'i7-forward/i5-forward':
        raise IndexNormalizationError('index.catalogue_invalid', 'Unsupported local 10x index catalogue schema/orientation.')
    for name, entry in catalogue['entries'].items():
        assignments = entry.get('assignments', [])
        if len(assignments) != (4 if entry.get('kind') == 'single' else 1):
            raise IndexNormalizationError('index.catalogue_invalid', 'Incomplete catalogue entry {!r}.'.format(name))
        pairs = [(item.get('index'), item.get('index2')) for item in assignments]
        if len(set(pairs)) != len(pairs) or any(not re.fullmatch('[ACGT]+', i7 or '') or
                (entry['kind'] == 'dual' and not re.fullmatch('[ACGT]+', i5 or '')) or
                (entry['kind'] == 'single' and i5) for i7, i5 in pairs):
            raise IndexNormalizationError('index.catalogue_invalid', 'Invalid catalogue assignment {!r}.'.format(name))
    catalogue['sha256'] = hashlib.sha256(content).hexdigest()
    return catalogue


def catalogue_identity(catalogue=None):
    catalogue = catalogue or load_catalogue()
    return {key: copy.deepcopy(catalogue[key]) for key in ('schema_version', 'version', 'sha256', 'orientation', 'sources')}


def normalize_indexes(index, index2='', *, i5_orientation='forward', catalogue=None):
    """Return every paired assignment, never a Cartesian product or renamed sample.

    A dual name belongs in index; index2 may be empty, the same name, or its exact
    expected sequence. Mixed explicit/named pairs and partial names fail closed.
    Supported families are GA (96 four-oligo wells) and TT (96 dual pairs).
    """
    if i5_orientation not in ('forward', 'reverse-complement'):
        raise IndexNormalizationError('index.orientation', 'Choose i5 orientation forward or reverse-complement explicitly.')
    index, index2 = str(index or ''), str(index2 or '')
    if index.startswith('SI-'):
        catalogue = catalogue or load_catalogue()
        entry = catalogue['entries'].get(index)
        if entry is None:
            raise IndexNormalizationError('index.unknown_name', 'Unknown/unsupported 10x index {!r}; supply verified explicit sequences or select the documented legacy mkfastq route.'.format(index))
        assignments = copy.deepcopy(entry['assignments'])
        if i5_orientation == 'reverse-complement':
            for item in assignments:
                item['index2'] = reverse_complement(item['index2'])
        if index2 and (entry['kind'] == 'single' or index2 not in (index, assignments[0]['index2'])):
            raise IndexNormalizationError('index.conflicting_pair', 'Index2 conflicts with the complete paired mapping for {!r}; use the same name, an empty cell, or its verified oriented i5 sequence.'.format(index))
        return assignments
    if index2.startswith('SI-'):
        raise IndexNormalizationError('index.incomplete_pair', 'A named 10x index must be supplied in index; do not mix a literal i7 with a symbolic i5.')
    for column, value in (('index', index), ('index2', index2)):
        if value and re.fullmatch('[ACGTNacgtn]+', value) is None:
            raise IndexNormalizationError('index.invalid_sequence', '{} must contain nucleotide bases without spaces, or a supported complete 10x index name.'.format(column))
    return [dict(index=index.upper(), index2=index2.upper())]


def normalize_rows(records, *, i5_orientation='forward', catalogue=None):
    """Expand rows retaining exact sample/project/lane, settings and source row."""
    catalogue = catalogue or load_catalogue()
    normalized = []
    for record in records:
        assignments = normalize_indexes(record.get('index', ''), record.get('index2', ''),
                                        i5_orientation=i5_orientation, catalogue=catalogue)
        for ordinal, assignment in enumerate(assignments, 1):
            row = copy.deepcopy(record)
            row.update(assignment)
            row['_index_provenance'] = dict(original_index=record.get('index', ''), original_index2=record.get('index2', ''),
                                            oligo=ordinal, i5_orientation=i5_orientation,
                                            representation='catalogue' if str(record.get('index', '')).startswith('SI-') else 'explicit',
                                            catalogue=catalogue_identity(catalogue))
            normalized.append(row)
    return normalized


def expand_samplesheet(content):
    """Materialize named rows for an explicit sequence edit, retaining labels.

    Returns original bytes when no symbolic cells occur. Only the new expanded
    representation is serialized; callers retain original bytes as their backup.
    The metadata parser is reused lazily to keep the normalizer independently usable.
    """
    import csv
    import io
    from configmaker.validation import ValidationResult, parse_samplesheet

    raw = content.decode('utf-8-sig') if isinstance(content, bytes) else content
    if not re.search(r'SI-[A-Z0-9]+-[A-H][0-9]+', raw):
        return content
    result = ValidationResult()
    parsed = parse_samplesheet(content, '<memory>', result)
    if not result.ok or parsed is None:
        raise IndexNormalizationError('index.invalid_sheet', result.render_text())
    named = [row for row in parsed['records'] if str(row.get('index', '')).startswith('SI-') or str(row.get('index2', '')).startswith('SI-')]
    if not named:
        return content
    orientation = parsed['options'].get('Index2Orientation')
    if any(len(normalize_indexes(row.get('index'), row.get('index2', ''))[0]['index2']) for row in named) and not orientation:
        raise IndexNormalizationError('index.orientation', 'Named dual indexes require an explicit Index2Orientation,forward or reverse-complement before correction.')
    normalized = normalize_rows(parsed['records'], i5_orientation=orientation or 'forward')
    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\r\n' if '\r\n' in raw else '\n')
    in_data, header_written = False, False
    for cells in csv.reader(io.StringIO(raw, newline='')):
        tag = cells[0].strip().lower() if cells else ''
        if tag.startswith('[') and tag.endswith(']'):
            in_data = tag in ('[data]', '[bclconvert_data]')
            writer.writerow(cells)
        elif in_data:
            if not cells or not any(cells):
                continue
            if not header_written:
                columns = list(parsed['columns'])
                for column in ('index', 'index2', 'I7_Index_ID'):
                    if column not in columns:
                        columns.append(column)
                writer.writerow(columns)
                for row in normalized:
                    if row['_index_provenance']['representation'] == 'catalogue':
                        row['I7_Index_ID'] = row['_index_provenance']['original_index']
                    writer.writerow([row.get(column, '') for column in columns])
                header_written = True
        else:
            writer.writerow(cells)
    encoded = output.getvalue().encode('utf-8')
    return (b'\xef\xbb\xbf' + encoded) if isinstance(content, bytes) and content.startswith(b'\xef\xbb\xbf') else encoded
