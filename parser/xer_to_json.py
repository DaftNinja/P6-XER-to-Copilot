import csv
import io
import json
import os
from datetime import datetime

def parse_p6_xer(file_path: str) -> dict:
    """
    Parses a native Oracle Primavera P6 .xer file.
    
    IMPORTANT: .xer files are TAB-DELIMITED TEXT files, NOT XML.
    This parser reads the file line-by-line, identifying sections by
    the section header (e.g., [PROJECT], [ACTIVITY]) and splitting
    subsequent lines by tabs to extract key-value pairs.
    
    Args:
        file_path (str): The absolute or relative path to the .xer file.
        
    Returns:
        dict: A JSON-serializable dictionary containing project metadata and activities.
    """
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    
    project_data = {}
    activities = []
    wbs_map = {}
    
    # Track current section
    current_section = None
    # Track if we are in the data rows of a section
    in_data = False
    # Header fields for the current section
    current_fields = []
    
    try:
        # P6 XER files can be ASCII, ANSI, or UTF-8. 'latin-1' is a safe fallback 
        # that rarely fails on binary-ish characters in these text files.
        # 'utf-8-sig' handles BOM if present.
        with open(file_path, 'r', encoding='utf-8-sig', errors='replace') as f:
            lines = f.readlines()
        
        # P6 XER structure:
        # Line 1: Header version info (e.g., "1")
        # Line 2: Blank or comment
        # Line 3: [SECTION_NAME]
        # Line 4: Field1\tField2\tField3...
        # Line N: Value1\tValue2\tValue3...
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines or lines starting with '!' (comments)
            if not line or line.startswith('!') or line.startswith('//'):
                i += 1
                continue
                
            # Check for Section Header (starts with [ and ends with ])
            if line.startswith('[') and line.endswith(']'):
                current_section = line[1:-1].upper()
                in_data = False
                current_fields = []
                i += 1
                
                # Next line should be the field names
                if i < len(lines):
                    field_line = lines[i].strip()
                    # The field line might be empty or contain tabs
                    if field_line:
                        current_fields = [f.strip() for f in field_line.split('\t')]
                    in_data = True
                    i += 1
                continue
            
            # If we are in data mode and have fields, process the row
            if in_data and current_fields and line:
                values = line.split('\t')
                # Create a dictionary for this row
                row_data = {}
                for idx, field in enumerate(current_fields):
                    if idx < len(values):
                        # Handle empty values
                        val = values[idx].strip()
                        row_data[field] = val if val else None
                    else:
                        row_data[field] = None
                
                # Process based on section
                if current_section == 'PROJECT':
                    # Usually only one main project in a snapshot, or we merge
                    if 'PROJECT_ID' in row_data:
                        project_data[row_data['PROJECT_ID']] = row_data
                        # Also store a reference to the primary project
                        if 'primary_project' not in project_data:
                            project_data['primary_project'] = row_data['PROJECT_ID']
                            
                elif current_section == 'WBS':
                    wbs_id = row_data.get('WBS_ID')
                    wbs_name = row_data.get('WBS_NAME', 'Unknown')
                    if wbs_id:
                        wbs_map[wbs_id] = wbs_name
                        
                elif current_section == 'ACTIVITY':
                    # Build the activity object
                    act = {
                        'id': row_data.get('ACTIVITY_ID'),
                        'code': row_data.get('ACTIVITY_CODE'),
                        'name': row_data.get('ACTIVITY_NAME'),
                        'wbs_id': row_data.get('WBS_ID'),
                        'status': row_data.get('STATUS'),
                        'pct_complete': float(row_data.get('COMPLETE_PCT', 0) or 0),
                        'duration': float(row_data.get('DURATION', 0) or 0),
                        'early_start': row_data.get('EARLY_START_DATE'),
                        'early_finish': row_data.get('EARLY_FINISH_DATE'),
                        'late_start': row_data.get('LATE_START_DATE'),
                        'late_finish': row_data.get('LATE_FINISH_DATE'),
                        'total_float': float(row_data.get('TOTAL_FLOAT', 0) or 0),
                        'free_float': float(row_data.get('FREE_FLOAT', 0) or 0),
                        'is_critical': row_data.get('IS_CRITICAL') == '1',
                        'baseline_finish': row_data.get('BASELINE_FINISH_DATE'),
                        'p20_finish': row_data.get('P20_FINISH_DATE'),
                        'p50_finish': row_data.get('P50_FINISH_DATE'),
                        'p80_finish': row_data.get('P80_FINISH_DATE')
                    }
                    
                    # Resolve WBS Name
                    act['wbs_name'] = wbs_map.get(act['wbs_id'], 'Unknown')
                    
                    # Store activity ID for predecessor lookup later
                    activities.append(act)
                
                # Move to next line
                i += 1
                continue
            
            # If line doesn't fit the above logic, skip it
            i += 1
            
    except Exception as e:
        return {"error": f"Error parsing XER file: {str(e)}"}

    # Second pass: Add predecessors to activities
    # P6 stores predecessors in a separate [PREDECESSOR] section
    # We need to re-scan or handle it in the first pass. 
    # Let's refine the first pass to capture predecessors if the section exists.
    
    # NOTE: The above loop skips [PREDECESSOR] section data. 
    # We need to modify the loop to capture PREDECESSOR sections.
    # Let's restart with a more robust 2-pass approach or modify the section handler.
    
    # --- RE-IMPLEMENTATION WITH PREDECESSOR SUPPORT ---
    # Let's do it properly. I will rewrite the parser to handle predecessors correctly.
    
    return {
        "project": project_data,
        "activities": activities,
        "metadata": {
            "parsed_at": datetime.now().isoformat(),
            "activity_count": len(activities),
            "source_file": os.path.basename(file_path),
            "warning": "Predecessors not yet linked in this version. See note."
        }
    }

# --- CORRECTED FULL IMPLEMENTATION WITH PREDECESSORS ---

def parse_p6_xer_complete(file_path: str) -> dict:
    """
    Robust parser for native P6 .xer files (Tab-Delimited).
    Handles PROJECT, WBS, ACTIVITY, and PREDECESSOR sections.
    """
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
        
    project_data = {}
    activities_dict = {} # Store by ID to link predecessors later
    wbs_map = {}
    predecessors_list = []
    
    current_section = None
    current_fields = []
    in_data = False
    
    try:
        with open(file_path, 'r', encoding='utf-8-sig', errors='replace') as f:
            lines = f.readlines()
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip comments/empties
            if not line or line.startswith('!') or line.startswith('//'):
                i += 1
                continue
                
            # Section Header
            if line.startswith('[') and line.endswith(']'):
                current_section = line[1:-1].upper()
                in_data = False
                current_fields = []
                i += 1
                
                if i < len(lines):
                    field_line = lines[i].strip()
                    if field_line:
                        current_fields = [f.strip() for f in field_line.split('\t')]
                    in_data = True
                    i += 1
                continue
            
            # Data Row
            if in_data and current_fields and line:
                values = line.split('\t')
                row_data = {}
                for idx, field in enumerate(current_fields):
                    val = values[idx].strip() if idx < len(values) else None
                    row_data[field] = val if val else None
                
                if current_section == 'PROJECT':
                    proj_id = row_data.get('PROJECT_ID')
                    if proj_id:
                        project_data[proj_id] = row_data
                        
                elif current_section == 'WBS':
                    wbs_id = row_data.get('WBS_ID')
                    if wbs_id:
                        wbs_map[wbs_id] = row_data.get('WBS_NAME', 'Unknown')
                        
                elif current_section == 'ACTIVITY':
                    act_id = row_data.get('ACTIVITY_ID')
                    if act_id:
                        activities_dict[act_id] = {
                            'id': act_id,
                            'code': row_data.get('ACTIVITY_CODE'),
                            'name': row_data.get('ACTIVITY_NAME'),
                            'wbs_id': row_data.get('WBS_ID'),
                            'status': row_data.get('STATUS'),
                            'pct_complete': float(row_data.get('COMPLETE_PCT', 0) or 0),
                            'duration': float(row_data.get('DURATION', 0) or 0),
                            'early_start': row_data.get('EARLY_START_DATE'),
                            'early_finish': row_data.get('EARLY_FINISH_DATE'),
                            'late_start': row_data.get('LATE_START_DATE'),
                            'late_finish': row_data.get('LATE_FINISH_DATE'),
                            'total_float': float(row_data.get('TOTAL_FLOAT', 0) or 0),
                            'free_float': float(row_data.get('FREE_FLOAT', 0) or 0),
                            'is_critical': row_data.get('IS_CRITICAL') == '1',
                            'baseline_finish': row_data.get('BASELINE_FINISH_DATE'),
                            'p20_finish': row_data.get('P20_FINISH_DATE'),
                            'p50_finish': row_data.get('P50_FINISH_DATE'),
                            'p80_finish': row_data.get('P80_FINISH_DATE'),
                            'predecessors': [] # List to be populated later
                        }
                        
                elif current_section == 'PREDECESSOR':
                    # P6 Pred Structure: ACTIVITY_ID (Successor) and SUCCESSOR_ID or PREDECESSOR_ID?
                    # Typically: ACTIVITY_ID is the Successor, and the other ID is the Predecessor.
                    # Fields vary by version, commonly: 'ACTIVITY_ID', 'SUCCESSOR_ID' or 'PREDECESSOR_ID'
                    # Let's look for 'ACTIVITY_ID' (Successor) and 'PREDECESSOR_ID' or 'SUCCESSOR_ID'
                    succ_id = row_data.get('ACTIVITY_ID')
                    pred_id = row_data.get('PREDECESSOR_ID') or row_data.get('SUCCESSOR_ID') 
                    # Note: Some exports name the fields differently. 
                    # Common fields: ACTIVITY_ID, SUCCESSOR_ID, RELATION_TYPE, LAG
                    # If 'PREDECESSOR_ID' is not present, check 'SUCCESSOR_ID' might be the link to previous.
                    # Actually, in P6 XER, the [PREDECESSOR] section usually lists:
                    # ACTIVITY_ID (The activity that HAS the predecessor)
                    # SUCCESSOR_ID (This is confusingly named, often holds the PREDECESSOR activity ID in some versions)
                    # Let's assume:
                    # Field 'ACTIVITY_ID' = The activity being defined (Successor)
                    # Field 'SUCCESSOR_ID' or 'PREDECESSOR_ID' = The ID of the task it depends on.
                    
                    # Let's check common P6 XER predecessor fields:
                    # ACTIVITY_ID, SUCCESSOR_ID (often this is actually the predecessor ID in raw dumps), RELATION_TYPE, LAG
                    # To be safe, we look for a field that isn't the main activity ID.
                    # Let's try both common keys.
                    pred_ref = row_data.get('PREDECESSOR_ID') or row_data.get('SUCCESSOR_ID')
                    
                    if succ_id and pred_ref:
                        # Ensure the successor activity exists in our dict
                        if succ_id in activities_dict:
                            activities_dict[succ_id]['predecessors'].append({
                                'id': pred_ref,
                                'type': row_data.get('RELATION_TYPE', 'FS'),
                                'lag': float(row_data.get('LAG', 0) or 0)
                            })
                
                i += 1
                continue
                
            i += 1
            
    except Exception as e:
        return {"error": f"Error parsing XER file: {str(e)}"}
        
    # Finalize activities list
    activities_list = list(activities_dict.values())
    for act in activities_list:
        act['wbs_name'] = wbs_map.get(act['wbs_id'], 'Unknown')
        
    return {
        "project": project_data,
        "activities": activities_list,
        "metadata": {
            "parsed_at": datetime.now().isoformat(),
            "activity_count": len(activities_list),
            "source_file": os.path.basename(file_path),
            "format": "P6 Native XER (Tab-Delimited)"
        }
    }

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python xer_to_json.py <path_to_xer_file>")
        sys.exit(1)
        
    file_path = sys.argv[1]
    result = parse_p6_xer_complete(file_path)
    
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        print(f"Successfully parsed {result['metadata']['activity_count']} activities.")
        primary_proj = result['project'].get('primary_project') if 'primary_project' in result['project'] else list(result['project'].keys())[0] if result['project'] else 'Unknown'
        if primary_proj in result['project']:
            print(f"Project: {result['project'][primary_proj].get('PROJECT_NAME', 'Unknown')}")
            
        output_file = "p6_analysis.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"JSON saved to {output_file}")
