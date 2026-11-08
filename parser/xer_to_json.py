import xml.etree.ElementTree as ET
import json
import os
from datetime import datetime

def parse_xer_file(file_path: str) -> dict:
    """
    Parses a native Oracle Primavera P6 .xer file into a structured JSON dictionary.
    
    Args:
        file_path (str): The absolute or relative path to the .xer file.
        
    Returns:
        dict: A JSON-serializable dictionary containing project metadata and activities.
    """
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    
    try:
        # 1. Read the file content
        # P6 XER files are XML with a specific format.
        # Sometimes they have a BOM (Byte Order Mark) or header comments.
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            content = f.read()
        
        # 2. Clean up the content
        # P6 files often start with <?xml version="1.0" encoding="UTF-8"?>
        # and may have comments. ET.fromstring handles standard XML headers well.
        # However, some P6 files include non-XML text at the very beginning in rare cases.
        # We'll assume standard XML format for now.
        
        # 3. Parse XML
        root = ET.fromstring(content)
        
        # 4. Extract Project Data
        project_data = {}
        # Project elements are usually under <PROJECT>
        # Note: P6 XER has <PROJECTS><PROJECT> ... </PROJECT></PROJECTS>
        projects_nodes = root.findall('.//PROJECT')
        if projects_nodes:
            # Take the first project (XER usually contains one project snapshot)
            project_node = projects_nodes[0]
            for tag in project_node:
                # Ignore nested structures like ACTIVITY, RESOURCE, etc.
                if tag.tag in ['ACTIVITY', 'RESOURCE', 'WBS', 'CALENDAR', 'USER', 'PROJECT']:
                    continue
                project_data[tag.tag] = tag.text if tag.text is not None else None
            
            # Extract Project Summary Info (optional)
            # e.g., PROJECT_NAME, STATUS, etc. are often direct children.

        # 5. Extract Activities
        activities = []
        # Activities are under <ACTIVITY_SUMMARY> and <ACTIVITY>
        # We primarily care about <ACTIVITY> for detailed data.
        
        # Build a map of WBS names for context (optional but helpful)
        wbs_map = {}
        for wbs in root.findall('.//WBS'):
            wbs_id = wbs.findtext('WBS_ID')
            wbs_name = wbs.findtext('WBS_NAME')
            if wbs_id and wbs_name:
                wbs_map[wbs_id] = wbs_name

        for activity in root.findall('.//ACTIVITY'):
            def get_text(tag_name):
                el = activity.find(tag_name)
                return el.text if el is not None and el.text is not None else None

            # Get WBS Name
            wbs_id = get_text('WBS_ID')
            wbs_name = wbs_map.get(wbs_id, "Unknown")
            
            act_data = {
                'ID': get_text('ACTIVITY_ID'),
                'Code': get_text('ACTIVITY_CODE'),
                'Name': get_text('ACTIVITY_NAME'),
                'WBS': wbs_name,
                'Status': get_text('STATUS') or 'NOT_STARTED',
                'PctComplete': float(get_text('COMPLETE_PCT') or 0),
                'Duration': float(get_text('DURATION') or 0),
                'EarlyStart': get_text('EARLY_START_DATE'),
                'EarlyFinish': get_text('EARLY_FINISH_DATE'),
                'LateStart': get_text('LATE_START_DATE'),
                'LateFinish': get_text('LATE_FINISH_DATE'),
                'TotalFloat': float(get_text('TOTAL_FLOAT') or 0),
                'FreeFloat': float(get_text('FREE_FLOAT') or 0),
                'IsCritical': get_text('IS_CRITICAL') == '1',
                'BaselineFinish': get_text('BASELINE_FINISH_DATE'),
                'P20Finish': get_text('P20_FINISH_DATE'),
                'P50Finish': get_text('P50_FINISH_DATE'),
                'P80Finish': get_text('P80_FINISH_DATE')
            }
            
            # Parse Predecessors
            predecessors = []
            for pred in activity.findall('.//PREDECESSOR'):
                def get_pred_text(tag_name):
                    el = pred.find(tag_name)
                    return el.text if el is not None and el.text is not None else None
                
                # Skip if predecessor ID is missing
                pred_id = get_pred_text('ACTIVITY_ID')
                if pred_id:
                    predecessors.append({
                        'ID': pred_id,
                        'Type': get_pred_text('RELATION_TYPE') or 'FS',
                        'Lag': float(get_pred_text('LAG') or 0)
                    })
            
            act_data['Predecessors'] = predecessors
            
            # Only add if it has an ID (skip empty nodes)
            if act_data['ID']:
                activities.append(act_data)

        return {
            "project": project_data,
            "activities": activities,
            "metadata": {
                "parsed_at": datetime.now().isoformat(),
                "activity_count": len(activities),
                "source_file": os.path.basename(file_path)
            }
        }
    
    except ET.ParseError as e:
        return {"error": f"XML Parsing Error: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected Error: {str(e)}"}

# Example usage for local testing
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python xer_to_json.py <path_to_xer_file>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    result = parse_xer_file(file_path)
    
    if "error" in result:
        print(f"Error: {result['error']}")
    else:
        # Print a summary
        print(f"Successfully parsed {result['metadata']['activity_count']} activities.")
        print(f"Project: {result['project'].get('PROJECT_NAME', 'Unknown')}")
        
        # Save to JSON for inspection
        output_file = "p6_analysis.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        print(f"JSON saved to {output_file}")
