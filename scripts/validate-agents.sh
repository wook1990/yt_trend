#!/bin/sh

set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DEFAULT_SRC_DIR="$ROOT_DIR/agents-src"
SRC_DIR="${WORKSPACE_AGENTS_DIR:-$DEFAULT_SRC_DIR}"

if [ ! -d "$SRC_DIR" ]; then
  echo "Missing source directory: $SRC_DIR" >&2
  exit 1
fi

allowed_domains="mobile admin backend-data backend-api desktop data-science product ops"
allowed_roles="planner implementer reviewer"
root_files="planner.md implementer.md reviewer.md"

extract_field() {
  field_name=$1
  file_path=$2

  awk -F': ' -v key="$field_name" '
    BEGIN { in_header = 0 }
    $0 == "---" && in_header == 0 { in_header = 1; next }
    $0 == "---" && in_header == 1 { exit }
    in_header == 1 && $1 == key { print substr($0, length(key) + 3); exit }
  ' "$file_path"
}

has_word() {
  needle=$1
  shift
  for item in "$@"; do
    if [ "$item" = "$needle" ]; then
      return 0
    fi
  done
  return 1
}

fail=0
tmp_list=$(mktemp)
find "$SRC_DIR" -type f -name '*.md' | sort > "$tmp_list"

while IFS= read -r file_path; do
  rel_path=${file_path#$SRC_DIR/}
  dir_name=$(dirname "$rel_path")
  base_name=$(basename "$rel_path")
  stem_name=${base_name%.md}

  case "$stem_name" in
    *[!a-z0-9-]*)
      echo "Invalid filename characters: $rel_path" >&2
      fail=1
      ;;
  esac

  if [ "$dir_name" = "." ]; then
    if ! has_word "$base_name" $root_files; then
      echo "Invalid root agent filename: $rel_path" >&2
      fail=1
    fi
  else
    if ! has_word "$dir_name" $allowed_domains; then
      echo "Invalid domain folder: $rel_path" >&2
      fail=1
    fi

    role=${stem_name##*-}
    if ! has_word "$role" $allowed_roles; then
      echo "Invalid role suffix: $rel_path" >&2
      fail=1
    fi
  fi

  name_field=$(extract_field "name" "$file_path")
  title_field=$(extract_field "title" "$file_path")
  description_field=$(extract_field "description" "$file_path")

  if [ -z "$name_field" ] || [ -z "$title_field" ] || [ -z "$description_field" ]; then
    echo "Missing frontmatter fields: $rel_path" >&2
    fail=1
  fi

  if [ "$name_field" != "$stem_name" ]; then
    echo "Frontmatter name mismatch: $rel_path" >&2
    fail=1
  fi
done < "$tmp_list"

rm -f "$tmp_list"

if [ "$fail" -ne 0 ]; then
  exit 1
fi

echo "Agent taxonomy validation passed: $SRC_DIR"
