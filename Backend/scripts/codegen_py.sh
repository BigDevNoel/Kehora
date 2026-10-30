#!/usr/bin/env bash
# Generate Pydantic v2 models from Backend/schemas/*.schema.json.
# Run from Backend/ (make codegen does this).
set -euo pipefail

out=schemas/kehora_schemas/generated
src=$(mktemp -d)
trap 'rm -rf "$src"' EXIT
cp schemas/*.schema.json "$src"/

rm -rf "$out"
uv run datamodel-codegen \
  --input "$src" \
  --input-file-type jsonschema \
  --output "$out" \
  --output-model-type pydantic_v2.BaseModel \
  --target-python-version 3.12 \
  --use-standard-collections \
  --use-union-operator \
  --use-title-as-name \
  --use-schema-description \
  --use-double-quotes \
  --field-constraints \
  --strict-nullable \
  --disable-timestamp \
  --formatters ruff-format ruff-check
touch schemas/kehora_schemas/py.typed
