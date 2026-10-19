"""
http://pep.databio.org/
"""

import os
import re
import oyaml as yaml

#import peppy
import pandas as pd

BASE = ['project_id',
        'src_project_id',
        'organism',
        'organism_inventory',
        'metadata_inputs',
        'samplesheet_options']

RUN =  ['workflow',
        'machine',
        'read_geometry',
        'run_read_geometry',
        'libprep_selection']

LIBPREP = ['adapter',
           'adapter2',
           'read_orientation',
           'libprepkit',
           'molecule',
           'library_strategy',
           'library_selection',
           'library_source',
           'library_strand']

STUDY = ['experiment_title',
         'experiment_summary',
         'experiment_principal_inverstigator',
         'experiment_contributor']



def config_info(config):
    single_cell = False
    subsamples = False
    multiple_projects = False
    multiple_flowcells = False
    
    for sample_id, sample_conf in config['samples'].items():
        if 'I1' in sample_conf:
            single_cell = True
        if ',' in sample_conf.get('R1', ''):
            subsamples = True
        if ',' in sample_conf.get('R2', ''):
            subsamples = True
        if ',' in sample_conf.get('Project_ID', ''):
            if len(set(sample_conf['Project_ID'].split(','))) > 1: 
                multiple_projects = True
        if ',' in sample_conf.get('Flowcell_ID', ''):
            if len(set(sample_conf['Flowcell_ID'].split(','))) > 1: 
                multiple_flowcells = True
    return {'subsamples': subsamples, 'multiple_projects':multiple_projects, 'multiple_flowcells': multiple_flowcells, 'single_cell':single_cell}

def _empty_col(col):
    if all(col==''):
        return True
    if col.isna().all():
        return True
    if col.isnull().all():
        return True
    return False

def _varying(config, column):
    return any(len(set(sample.get(column, "").split(","))) > 1 for sample in config["samples"].values())


def conifg2sampletable(config, info, drop_empty_cols=True):
    """Return sample metadata with PEP tokens for the actual discovered reads."""
    df = pd.DataFrame.from_dict(config["samples"], orient="index")
    if drop_empty_cols:
        df = df.loc[:, ~df.apply(_empty_col, axis=0)]
    if info["subsamples"]:
        df = df.drop(columns=[column for column in df if column.endswith("_md5sum")])
        for column in ("Flowcell_Name", "Flowcell_ID", "Project_ID", "Src_Project_ID"):
            if column in df:
                if _varying(config, column):
                    df = df.drop(columns=column)
                else:
                    df[column] = df[column].map(lambda value: value.split(",")[0])
    for read in ("R1", "R2", "I1"):
        if read in df:
            if not info["subsamples"]:
                df["_" + read + "_source"] = df[read]
            df[read] = read
    return df.set_index("Sample_ID").reset_index().rename(columns={"Sample_ID": "sample_name"})


def config2subsampletable(config, info):
    """Keep read ordering, checksums and varying source metadata together."""
    if not info["subsamples"]:
        # Preserve this exported helper's single-read return for direct callers;
        # create_peppy writes this table only when subsamples are present.
        rows = [{"sample_name": sid, "subsample_name": "{}_1".format(sid)} for sid in config["samples"]]
        return pd.DataFrame(rows) if rows else None
    rows = []
    metadata = [column for column in ("Flowcell_Name", "Flowcell_ID", "Project_ID", "Src_Project_ID") if _varying(config, column)]
    for sample_id, sample in config["samples"].items():
        reads = {read: sample.get(read, "").split(",") for read in ("R1", "R2", "I1")}
        count = max(len(paths) for paths in reads.values())
        for index in range(count):
            row = {"subsample_name": "{}_{}".format(sample_id, index + 1), "sample_name": sample_id}
            for read, paths in reads.items():
                if paths[0] and index < len(paths):
                    row["_" + read + "_source"] = paths[index]
                    sums = sample.get(read + "_md5sum", "").split(",")
                    if sums[0] and len(sums) == len(paths):
                        row[read + "_md5sum"] = sums[index]
            for column in metadata:
                values = sample.get(column, "").split(",")
                row[column] = values[index] if len(values) == count else values[0]
            if info["single_cell"] and index < len(reads["R1"]):
                lane = re.search(r"_(S\d+)_(L\d{3})_R1_001\.fastq\.gz$", reads["R1"][index])
                if lane:
                    row["run_number"], row["lane"] = lane.groups()
            rows.append(row)
    return pd.DataFrame(rows)


def config2experimentinfo(config):
    """extract global experiment/data info
    """
    exp_dict = {}
    for k in BASE:
        if k in config:
            exp_dict[k] = config[k]
    for n in STUDY:
        if n in config:
            exp_dict[n] = config[n]        
    for k in RUN:
        if k in config:
            exp_dict[k] = config[k]
    for n in LIBPREP:
        if n in config:
            exp_dict[n] = config[n]
    
    exp_dict['protocol'] = config.get('protocol', {})
    exp_dict['descriptors'] = config.get('descriptors', {})
    return exp_dict
        

def peppy_project_dict(config, info):
    """return project config dictionary
    """
    
    peppy_project = {}
    peppy_project['pep_version'] = '2.0.0'
    peppy_project['sample_table'] = 'sample_table.csv'
    global_params = config2experimentinfo(config)
    peppy_project.update(global_params)
    
    if info['subsamples']:
        peppy_project['subsample_table'] = 'subsample_table.csv'
    derive = {}
    derive['attributes'] = ['R1', 'R2', 'I1']
    sources = {read: "{_" + read + "_source}" for read in ("R1", "R2", "I1")}
    derive['sources'] = sources
    peppy_project['sample_modifiers'] = {}
    peppy_project['sample_modifiers']['derive'] = derive
    return peppy_project
    

def create_peppy(config, output_dir='peppy_project'):
    """createa a peppy project directory
    """
    peppy_project = {}
    peppy_dir = output_dir or 'peppy_project'
    info = config_info(config)
    sampletable = conifg2sampletable(config, info)
    subsampletable = config2subsampletable(config, info)
    peppy_conf = peppy_project_dict(config, info)

    # write output
    os.makedirs(peppy_dir, exist_ok=True)
    sampletable.to_csv(os.path.join(peppy_dir, 'sample_table.csv'), index=None)
    if info['subsamples']:
        subsampletable.to_csv(os.path.join(peppy_dir, 'subsample_table.csv'), index=None)
    with open(os.path.join(peppy_dir, 'pep_config.yaml'), 'w') as fh:
        yaml.safe_dump(peppy_conf, fh)    
        
