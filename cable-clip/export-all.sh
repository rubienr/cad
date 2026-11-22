#!/usr/bin/env bash
set -u

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd) || exit 1

PARALLEL=$(nproc)

configs=(
    export-config-p-clip.py
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
