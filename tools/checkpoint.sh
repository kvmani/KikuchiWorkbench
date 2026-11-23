#!/usr/bin/env bash
# Commit all changes and push to the working branch and main (fast-forward only).
# Usage: tools/checkpoint.sh "commit message"
set -euo pipefail
msg="${1:?commit message required}"
branch="$(git rev-parse --abbrev-ref HEAD)"
git add -A
if ! git diff --cached --quiet; then
  git commit -q -m "$msg" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011oMNbFgKPXgg7QeRZ94JA1"
fi
push() {
  local n=0
  until git push -q -u origin "$1"; do
    n=$((n+1)); [ $n -ge 4 ] && return 1; sleep $((2**n))
  done
}
push "$branch"
push "HEAD:main"
git log --oneline -1
