#!/bin/sh

set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DEFAULT_SRC_DIR="$ROOT_DIR/agents-src"
SRC_DIR="${WORKSPACE_AGENTS_DIR:-$DEFAULT_SRC_DIR}"

if [ ! -d "$SRC_DIR" ]; then
  echo "Missing source directory: $SRC_DIR" >&2
  exit 1
fi

fail=0
tmp_list=$(mktemp)
find "$SRC_DIR" -type f -name '*.md' | sort > "$tmp_list"

check_contains() {
  pattern=$1
  file_path=$2
  label=$3

  if ! rg -q "^${pattern}$" "$file_path"; then
    echo "Missing ${label}: ${file_path#$SRC_DIR/}" >&2
    fail=1
  fi
}

while IFS= read -r file_path; do
  rel_path=${file_path#$SRC_DIR/}
  base_name=$(basename "$file_path")
  stem_name=${base_name%.md}

  check_contains "Your responsibilities:" "$file_path" "responsibilities heading"
  check_contains "Working style:" "$file_path" "working style heading"
  check_contains "Checklist:" "$file_path" "checklist heading"
  check_contains "Output expectations:" "$file_path" "output expectations heading"

  checklist_count=$(awk '
    BEGIN { in_block = 0; count = 0; done = 0 }
    /^Checklist:$/ { in_block = 1; next }
    in_block == 1 && /^Output expectations:$/ { print count; done = 1; exit }
    in_block == 1 && /^- / { count++ }
    END { if (in_block == 1 && done == 0) print count }
  ' "$file_path")

  if [ "${checklist_count:-0}" -lt 3 ]; then
    echo "Checklist too short: $rel_path" >&2
    fail=1
  fi

  desc=$(awk -F': ' '
    BEGIN { in_header = 0 }
    $0 == "---" && in_header == 0 { in_header = 1; next }
    $0 == "---" && in_header == 1 { exit }
    in_header == 1 && $1 == "description" { print substr($0, 14); exit }
  ' "$file_path")

  if [ -z "$desc" ]; then
    echo "Missing description: $rel_path" >&2
    fail=1
  fi

  case "$stem_name" in
    *planner)
      if ! printf '%s' "$desc" | rg -qi 'plan|sequence|scope|flow|phase|execution'; then
        echo "Planner description lacks planning language: $rel_path" >&2
        fail=1
      fi
      ;;
    *implementer)
      if ! printf '%s' "$desc" | rg -qi 'implement|change|update|build|make'; then
        echo "Implementer description lacks implementation language: $rel_path" >&2
        fail=1
      fi
      ;;
    *reviewer)
      if ! printf '%s' "$desc" | rg -qi 'review|bug|risk|regression|validation'; then
        echo "Reviewer description lacks review language: $rel_path" >&2
        fail=1
      fi
      ;;
  esac
done < "$tmp_list"

rm -f "$tmp_list"

if [ "$fail" -ne 0 ]; then
  exit 1
fi

echo "Agent quality lint passed: $SRC_DIR"
