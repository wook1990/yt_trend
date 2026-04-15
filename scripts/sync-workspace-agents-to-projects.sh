#!/bin/sh

set -eu

WORKSPACE_AGENTS_DIR="${WORKSPACE_AGENTS_DIR:-/Users/haram/workspace/agents}"

if [ "$#" -eq 0 ]; then
  echo "Usage: sh ./scripts/sync-workspace-agents-to-projects.sh <project_dir> [project_dir ...]" >&2
  exit 1
fi

for project_dir in "$@"; do
  if [ ! -d "$project_dir" ]; then
    echo "Skip: $project_dir (directory not found)" >&2
    continue
  fi

  if [ -x "$project_dir/scripts/sync-agents.sh" ]; then
    echo "Sync via script: $project_dir"
    (
      cd "$project_dir"
      WORKSPACE_AGENTS_DIR="$WORKSPACE_AGENTS_DIR" sh ./scripts/sync-agents.sh
    )
    continue
  fi

  if [ -f "$project_dir/package.json" ] && grep -q '"sync:workspace-agents"' "$project_dir/package.json"; then
    echo "Sync via npm script: $project_dir"
    (
      cd "$project_dir"
      npm run sync:workspace-agents
    )
    continue
  fi

  echo "Skip: $project_dir (no sync-agents.sh or sync:workspace-agents script)" >&2
done
