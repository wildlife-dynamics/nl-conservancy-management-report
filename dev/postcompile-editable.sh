#!/usr/bin/env bash
# Canonical copy: ~/MEP/infra/ecoscope-hub/template/dev/ — synced into workflow
# repos via ecoscope-hub dev/sync.sh; do not edit per-repo copies.
#
# Post-compile patches for editable-ecoscope dev mode (see ecoscope-spec.md
# "Editable dev-mode pitfalls"). Re-run after EVERY wt-compiler compile:
#   1. pydantic <2.9 (compiler emits <3.0.0; newer breaks apply_classification)
#   2. platforms -> osx-arm64 only (cross-platform pypi solves build sdists
#      that fail; dev runs are local-only anyway)
# Then installs the inner env. Test with: ./dev/run-test-cases.sh ... --frozen
set -euo pipefail

cd "$(dirname "$0")/.."
workflow_dir=$(ls -d ecoscope-workflows-*-workflow 2>/dev/null | head -1)
if [ -z "$workflow_dir" ]; then
    echo "ERROR: no ecoscope-workflows-*-workflow dir found" >&2
    exit 1
fi

python3 - "$workflow_dir/pixi.toml" <<'EOF'
import re, sys
path = sys.argv[1]
s = open(path).read()
s = s.replace('version = ">=2.0.0,<3.0.0"', 'version = ">=2.0.0,<2.9.0"')
s = re.sub(r"platforms = \[[^\]]*\]", "platforms = ['osx-arm64']", s, count=1)
open(path, 'w').write(s)
print("patched", path)
EOF

cd "$workflow_dir"
pixi install
