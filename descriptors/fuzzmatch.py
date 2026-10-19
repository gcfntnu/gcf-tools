"""
"""
import os
import sys
import requests
import logging

from thefuzz import fuzz, process
import pandas as pd

logger = logging.getLogger('GCF-configmaker')

SERVER= "https://rest.ensembl.org"
ENS_ORG_DB = os.path.join(os.path.dirname(__file__), 'ens_org.pkl')
def fetch_ensembl_species(ext = "/info/species?", division='EnsemblVertebrates', db=None):
    kv_store = {}
    keep_keys = ['name', 'display_name', 'common_name', 'aliases']
    if division is not None:
        ext += 'division={}'.format(division)
    print(SERVER + ext)
    r = requests.get(SERVER + ext, headers={ "Content-Type" : "application/json"}) 
    if not r.ok:
        r.raise_for_status()
        sys.exit()
    decoded = r.json()
    species = decoded['species']
    for s in species:
        name = s.get('name')
        if name and '_' in name:
            genus_species = '_'.join(name.split('_')[:2])
        aliases = set(s.get('aliases', []))
        common_name = s.get('common_name')
        if common_name:
            aliases.add(common_name)
        strain = s.get('strain')
        if strain:
            aliases.add(strain)
        
        if None in aliases:
            aliases.remove(None)
        if genus_species != name:
            if strain is None:
                aliases.add(genus_species)
        kv_store[name] = list(aliases)
        
    logger.debug('found {} new species'.format(len(kv_store)))
    if db:
        db.update(kv_store)
        return db
    else:
        return kv_store

from descriptors.organisms import LegacyOrganismMapping, resolve_organism

ORG_DB = LegacyOrganismMapping()


def fuzzmatch_organism(query, min_score=80, min_letters=4):
    """Return an exact canonical/curated match, or None; fuzzy hits are suggestions only."""
    result = resolve_organism(query, min_score=min_score, min_letters=min_letters)
    if result.status in ('ambiguous', 'unresolved'):
        logger.warning('%s', result.diagnostic(query))
    return result.canonical


def fuzzmatch_reference(query, min_score=80):
    """
    Fuzzymatch common reference values
    """
    if pd.isnull(query) or query in ['N/A', 'NA', '', None]:
        return None
    keywords = ['control', 'ctrl', 'reference', 'wildtype', 'stable', 'zero', 'normal', 'healthy']
    name, score = process.extractOne(str(query).strip(), keywords)
    if score >= min_score:
        #print(name, score)
        logger.debug('identfied reference level {}'.format(query))
        return query
    return None
