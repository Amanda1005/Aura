import json
from dataclasses import asdict
from skill.skill import run

result = run(top_n=5)
print(json.dumps(asdict(result), indent=2, default=str))
