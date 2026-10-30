"""Write the FastAPI OpenAPI document to api/openapi.json (input to the TS client codegen)."""

import json
from pathlib import Path

from kehora_api.main import create_app
from kehora_common.settings import Settings

OUT = Path(__file__).resolve().parents[1] / "api" / "openapi.json"

if __name__ == "__main__":
    app = create_app(Settings(_env_file=None, log_level="WARNING"))
    OUT.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"openapi: wrote {OUT.name}")
