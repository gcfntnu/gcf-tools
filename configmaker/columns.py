"""Submission-workbook column mappings shared by all input consumers."""

def _customer_column_mapper(x):
    """
    map headers of customer-sheet to machine friendly headers
    """
    starts = [
        ("Unique", "Sample_ID"),
        ("External", "External_ID"),
        ("Sample Group", "Sample_Group"),
        ("Comment", "Customer_Comments"),
        ("Sample biosource", "Sample_Biosource"),
        ("Project", "Project_ID"),
        ("Sample type", "Sample_Type"),
        ("Sample Type", "Sample_Type"),
        ("Index (If libraries are submitted  indicate what index sequence is used P7 )","Index1",),
        ("Index2", "Index2"),
        ("Index1", "Index1"),
        ("Sequence1", "Index_Sequence1"),
        ("Sequence2", "Index_Sequence2"),
        ("Plate location", "Plate"),
        ("Sample buffer", "Sample_Buffer"),
        ("Sample Buffer", "Sample_Buffer"),
        ("Volume", "Volume"),
        ("Quantification", "Quantification"),
        ("Concentration", "Concentration"),
        ("260/280", "260/280"),
        ("260/230", "260/230"),
        ("Organism", "Organism"),
        ("RIN", "RIN"),
    ]
    for src, dst in starts:
        if x.startswith(src):
            return dst
    # unknown header value (may be customer added)
    src_sanitized = x.title()
    remove = """- ? ( ) [ ] / \ = + < > : ; " ' , * ^ | & .""".split()
    for r in remove:
        src_sanitized = src_sanitized.replace(r, "")
        src_sanitized = src_sanitized.replace(" ", "_")
    return "Submitted_" + src_sanitized


def _lab_column_mapper(x):
    """
    map headers of wetlab-sheet to machine friendly headers
    """
    starts = [
        ("Concentration", "Concentration"),
        ("260/280", "260/280"),
        ("260/230", "260/230"),
        ("Comment", "Comments"),
        ("Sample_ID", "Sample_ID"),
        ("Project", "Project_ID"),
        ("RIN", "RIN"),
        ("SpikeIn", "SpikeIn"),
        ("Fragment_Length", "Fragment_Length"),
        ("Fragment_SD", "Fragment_SD"),
        ("Sample_Name", "Lab_Sample_Name"),
        ("KIT", "KIT"),
        ("ERCC", "ERCC"),
    ]
    for src, dst in starts:
        if x.startswith(src):
            return dst
    src_sanitized = x.title()
    remove = """- ? ( ) [ ] / \ = + < > : ; " ' , * ^ | & .""".split()
    for r in remove:
        src_sanitized = src_sanitized.replace(r, "")
        src_sanitized = src_sanitized.replace(" ", "_")
    return "Lab_" + src_sanitized


def _demux_column_mapper(x):
    """
    map headers of demux-sheet to machine friendly headers
    """
    starts = [
        ("Unique", "Sample_ID"),
        ("Wells", "Wells"),
        ("External", "External_ID"),
        ("Sample Group", "Sample_Group"),
        ("Comment", "Customer_Comments"),
    ]
    for src, dst in starts:
        if x.startswith(src):
            return dst
    # unknown header value (may be customer added)
    src_sanitized = x.title()
    remove = """- ? ( ) [ ] / \ = + < > : ; " ' , * ^ | & .""".split()
    for r in remove:
        src_sanitized = src_sanitized.replace(r, "")
        src_sanitized = src_sanitized.replace(" ", "_")
    return "Demux_" + src_sanitized


