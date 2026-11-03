#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CANDIDATE=${SA_HOME:-$SCRIPT_DIR}
while [ -n "$CANDIDATE" ] && [ ! -f "$CANDIDATE/scripts/sa.py" ]; do
  PARENT=$(dirname "$CANDIDATE")
  if [ "$PARENT" = "$CANDIDATE" ]; then
    CANDIDATE=""
  else
    CANDIDATE=$PARENT
  fi
done
if [ -z "$CANDIDATE" ]; then
  echo "找不到 Study Arca scripts/sa.py；请设置 SA_HOME" >&2
  exit 1
fi

exec python "$CANDIDATE/scripts/sa.py" program "$@"
