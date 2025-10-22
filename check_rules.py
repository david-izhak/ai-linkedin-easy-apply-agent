import yaml
from pathlib import Path

rules_path = Path('config/rules.yaml')
if rules_path.exists():
    with open(rules_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    print(f'File exists: {rules_path.exists()}')
    print(f'Schema version: {data.get("schema_version")}')
    print(f'Rules count: {len(data.get("rules", []))}')
    print('✓ Rules file is valid')
else:
    print('✗ Rules file not found')

