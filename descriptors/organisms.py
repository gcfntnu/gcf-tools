"""Exact organism resolution from a fixed, validated, offline inventory."""
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
import copy
import hashlib
import json
from pathlib import Path
import re

import pandas as pd
from thefuzz import fuzz

RESOURCE = Path(__file__).with_name('organisms.json')
MISSING = {'', 'n/a', 'na', '<na>', 'nan', 'none', 'null'}


class OrganismInventoryError(RuntimeError):
    pass


def normalize(value):
    return re.sub(r'[\s_]+', ' ', str(value).strip().casefold())


def is_missing(value):
    return bool(pd.isna(value)) or normalize(value) in MISSING


@dataclass(frozen=True)
class Resolution:
    status: str
    canonical: str = None
    candidates: tuple = ()
    suggestions: tuple = ()
    inventory_sha256: str = ''
    components: tuple = ()

    def diagnostic(self, query):
        choices = self.candidates or self.suggestions
        detail = '; candidates: ' if self.candidates else '; suggestions: '
        return '{} organism {!r}{}{}. Use an exact canonical species key or an unambiguous curated alias.'.format(
            self.status.capitalize(), query, detail if choices else '', ', '.join(choices)) + ' Inventory sha256=' + self.inventory_sha256


class SpeciesInventory:
    """Validated resource bytes and their reproducible identity; no refresh or I/O on lookup."""
    def __init__(self, data, content):
        if not isinstance(data, dict) or type(data.get('schema_version')) is not int or data['schema_version'] != 1:
            raise OrganismInventoryError('Unsupported organism inventory schema; expected schema_version 1')
        if not isinstance(data.get('inventory_version'), str) or not data['inventory_version'].strip():
            raise OrganismInventoryError('Organism inventory needs a nonempty inventory_version')
        if not isinstance(data.get('provenance'), dict) or not data['provenance']:
            raise OrganismInventoryError('Organism inventory needs source provenance')
        species = data.get('species')
        if not isinstance(species, dict) or not species:
            raise OrganismInventoryError('Organism inventory needs a nonempty species mapping')
        self.species = species
        self.canonical, self.aliases = {}, defaultdict(set)
        for key, aliases in species.items():
            if not isinstance(key, str) or '__' in key or not re.fullmatch(r'[a-z0-9][a-z0-9_.-]*', key):
                raise OrganismInventoryError('Invalid canonical species key {!r}'.format(key))
            canonical = normalize(key)
            if canonical in self.canonical:
                raise OrganismInventoryError('Conflicting canonical species keys: ' + key)
            self.canonical[canonical] = key
            self.aliases[canonical].add(key)
            if not isinstance(aliases, list) or any(not isinstance(v, str) or not v.strip() or normalize(v) in MISSING for v in aliases):
                raise OrganismInventoryError('Invalid aliases for ' + key)
            for alias in aliases:
                self.aliases[normalize(alias)].add(key)
        curated = data.get('curated_aliases', {})
        declared = data.get('ambiguous_aliases', {})
        if not isinstance(curated, dict) or not isinstance(declared, dict):
            raise OrganismInventoryError('Invalid curated/ambiguous alias declarations')
        for alias, key in curated.items():
            if not isinstance(alias, str) or normalize(alias) != alias or not isinstance(key, str) or key not in species or key not in self.aliases.get(alias, set()):
                raise OrganismInventoryError('Invalid curated alias {!r}'.format(alias))
        collisions = {alias: sorted(keys) for alias, keys in self.aliases.items() if len(keys) > 1 and alias not in curated}
        if declared != collisions:
            raise OrganismInventoryError('Conflicting aliases: declare exact ambiguous_aliases or review explicit curated_aliases')
        self.curated = curated
        self.identity = {'schema_version': 1, 'inventory_version': data['inventory_version'],
                         'sha256': hashlib.sha256(content).hexdigest(), 'species_count': len(species),
                         'provenance': data['provenance']}

    def _resolution(self, *args, **kwargs):
        return Resolution(*args, inventory_sha256=self.identity['sha256'], **kwargs)

    def resolve(self, query, min_score=80, min_letters=4):
        if is_missing(query):
            return self._resolution('missing')
        if '__' in str(query):
            # The workflow's explicit mixed-reference separator is not a taxon.
            # Resolve every member independently; retain order and full strains.
            members = [self.resolve(part, min_score, min_letters) for part in str(query).split('__')]
            keys = tuple(member.canonical for member in members)
            if all(member.status == 'resolved' for member in members) and len(set(keys)) == len(keys):
                return self._resolution('mixed', '__'.join(keys), components=keys)
            ambiguous = {key for member in members for key in member.candidates}
            if ambiguous:
                return self._resolution('ambiguous', candidates=tuple(sorted(ambiguous)))
            suggestions = {key for member in members for key in member.suggestions}
            suggestions.update(member.canonical for member in members if member.canonical)
            return self._resolution('unresolved', suggestions=tuple(sorted(suggestions)))
        name = normalize(query)
        # Exact canonical keys also accept scientific-name spacing and case.
        if name in self.canonical:
            return self._resolution('resolved', self.canonical[name])
        if name in self.curated:
            return self._resolution('resolved', self.curated[name])
        keys = self.aliases.get(name, set())
        if len(keys) == 1:
            return self._resolution('resolved', next(iter(keys)))
        if keys:
            return self._resolution('ambiguous', candidates=tuple(sorted(keys)))
        scores = []
        for key, aliases in self.species.items():
            choices = [normalize(key)] + [normalize(a) for a in aliases if len(a) >= min_letters]
            score = max(fuzz.WRatio(name, choice) for choice in choices)
            if score >= min_score:
                scores.append((score, key))
        suggestions = tuple(key for score, key in sorted(scores, key=lambda pair: (-pair[0], pair[1]))[:5])
        return self._resolution('unresolved', suggestions=suggestions)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise OrganismInventoryError('Duplicate organism inventory key: ' + key)
        result[key] = value
    return result


def read_json(content):
    return json.loads(content, object_pairs_hook=_unique_object)


def load_inventory(path=None):
    """Explicit local selection is available to Python callers; identity always records its bytes."""
    path = Path(path) if path is not None else RESOURCE
    try:
        content = path.read_bytes()
        data = read_json(content)
    except (OSError, ValueError, UnicodeError) as error:
        raise OrganismInventoryError('Cannot read required organism inventory {}: {}. Reinstall gcf-tools or validate the explicitly selected local artifact.'.format(path, error)) from error
    return SpeciesInventory(data, content)


@lru_cache(maxsize=1)
def default_inventory():
    return load_inventory()


def resolve_organism(query, min_score=80, min_letters=4, inventory=None):
    return (inventory if inventory is not None else default_inventory()).resolve(query, min_score, min_letters)


def inventory_identity():
    return copy.deepcopy(default_inventory().identity)


class LegacyOrganismMapping(Mapping):
    """Read-only compatibility view of canonical keys and historical aliases."""
    def __getitem__(self, key):
        return list(default_inventory().species[key])

    def __iter__(self):
        return iter(default_inventory().species)

    def __len__(self):
        return len(default_inventory().species)

    def copy(self):
        return dict(self.items())
