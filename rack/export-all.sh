#!/usr/bin/env bash
set -u

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd) || exit 1

PARALLEL=$(nproc)

configs=(
    export-config-flat-lan-cable-clip.py
    export-config-round-cable-clip-1-row.py
    export-config-round-cable-clip-2-rows-combined.py
    export-config-round-cable-clip-2-rows.py
)

status=0

function run() 
{
    # Attempt every config and both modes, even if an earlier export fails.
    for config in "${configs[@]}"; do
        "$script_dir/export.py" --export --screenshot "$script_dir/$config" --parallel $PARALLEL || status=1
    done
}

time run
exit "$status"
