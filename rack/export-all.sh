#!/usr/bin/env bash
set -u

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd) || exit 1

configs=(
    export-config-flat-lan-cable-clip.py
    export-config-round-cable-clip-1-row.py
    export-config-round-cable-clip-2-rows-combined.py
    export-config-round-cable-clip-2-rows.py
)

# Attempt every config and both modes, even if an earlier export fails.
status=0
for config in "${configs[@]}"; do
    "$script_dir/export.py" "$script_dir/$config" || status=1
    "$script_dir/export.py" --screenshot "$script_dir/$config" || status=1
done

exit "$status"
