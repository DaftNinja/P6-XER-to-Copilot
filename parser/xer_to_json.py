import xml.etree.ElementTree as ET
import json
import base64
from datetime import datetime

def parse_xer_file(file_path: str) -> dict:
    """
    Parses a Primavera P6 XER file into a structured JSON dictionary.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Remove potential BOM
        if content.startswith('\ufeff'):
            content = content[1:]

        root = ET.fromstring(content)
        
        # Extract Project Data
        project_data = {}
        for project in root.findall('.//PROJECT'):
            for tag in project:
                project_data[tag.tag] = tag.text if tag.text is not None else None
        
        # Extract Activities
        activities = []
        for activity in root.findall('.//ACTIVITY'):
            def get_text(tag_name):
                el = activity.find(tag_name)
                return el.text if el is not None and el.text is not None else None

            act_data = {
                'ID': get_text('ACTIVITY_ID'),
                'Name': get_text('ACTIVITY_NAME'),
                'Code': get_text('ACTIVITY_CODE'),
                'Status': get_text('STATUS') or 'NOT_STARTED',
                'PctComplete': float(get_text('COMPLETE_PCT') or 0),
                'Duration': float(get_text('DURATION') or 0),
                'EarlyStart': get_text('EARLY_START_DATE'),
                'EarlyFinish': get_text('EARLY_FINISH_DATE'),
                'LateStart': get_text('LATE_START_DATE'),
                'LateFinish': get_text('LATE_FINISH_DATE'),
                'TotalFloat': float(get_text('TOTAL_FLOAT') or 0),
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
                predecessors.append({
                    'ID': get_pred_text('ACTIVITY_ID'),
                    'Type': get_pred_text('RELATION_TYPE') or 'FS',
                    'Lag': float(get_pred_text('LAG') or 0)
                })
            
            act_data['Predecessors'] = predecessors
            activities.append(act_data)

        return {
            "project": project_data,
            "activities": activities,
            "metadata": {
                "parsed_at": datetime.now().isoformat(),
                "activity_count": len(activities)
            }
        }
    
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python xer_to_json.py <path_to_xer_file>")
        sys.exit(1)
    
    result = parse_xer_file(sys.argv[1])
    print(json.dumps(result, indent=2))

