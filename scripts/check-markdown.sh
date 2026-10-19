#!/usr/bin/env bash
# Markdown lint guard for Daikin Cycle ML docs.
# Catches formatting pitfalls that silently break rendering:
#   tabs, trailing whitespace, CRLF, missing EOF newline, 3+ blank lines,
#   unclosed code fences, heading-level jumps, over-indented bullets,
#   over-indented headings/fences, 8+ leading spaces outside code fence,
#   mixed unordered list markers.
# Exit 0 on all-pass, 1 on any FAIL.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

FAIL=0
FILES=$(find . -name '*.md' \
    -not -path './.git/*' \
    -not -path '*/node_modules/*' \
    -not -path './.mypy_cache/*' \
    -not -path './.pytest_cache/*' \
    -not -path './__pycache__/*' \
    | sort)

if [[ -z "$FILES" ]]; then
    echo "[md] no markdown files found"
    exit 0
fi
COUNT=$(printf '%s\n' "$FILES" | wc -l | tr -d ' ')
echo "[md] scanning $COUNT file(s)"

report_fail() { echo "  FAIL [$1]: $2"; FAIL=1; }
report_warn() { echo "  WARN [$1]: $2"; }

check_file() {
    local f="$1"

    # 1. Tabs
    if grep -qP '\t' "$f" 2>/dev/null; then
        report_fail "$f" "contains tab characters (use spaces)"
        grep -nP '\t' "$f" | head -3 | sed 's/^/    /'
    fi

    # 2. Trailing whitespace (2 spaces = hard break is legal; 1 or 3+ is a bug)
    if grep -qP '[^ ]  +$' "$f" 2>/dev/null; then
        report_fail "$f" "3+ trailing spaces (only 2 = hard break allowed)"
        grep -nP '[^ ]  +$' "$f" | head -3 | sed 's/^/    /'
    fi
    if grep -qP '[^ ] $' "$f" 2>/dev/null; then
        report_fail "$f" "1 trailing space (remove, or use 2 for hard break)"
        grep -nP '[^ ] $' "$f" | head -3 | sed 's/^/    /'
    fi

    # 3. CRLF line endings
    if grep -qP '\r$' "$f" 2>/dev/null; then
        report_fail "$f" "CRLF line endings (use LF)"
    fi

    # 4. Missing final newline
    if [[ -s "$f" ]]; then
        local last_byte
        last_byte=$(tail -c1 "$f" | od -An -tx1 | tr -d ' \n')
        [[ "$last_byte" == "0a" ]] || report_fail "$f" "missing final newline at EOF"
    fi

    # 5. Max 2 consecutive blank lines
    awk '
        /^$/ { n++; if (n > 2) { printf "  FAIL [%s:%d]: 3+ consecutive blank lines\n", FILENAME, NR; bad = 1 } ; next }
        { n = 0 }
        END { if (bad) exit 1; exit 0 }
    ' "$f" || FAIL=1

    # 6. Balanced code fences (each style separately)
    local fc
    fc=$(grep -cE '^```' "$f" || true)
    (( fc % 2 == 0 )) || report_fail "$f" "unclosed backtick fence ($fc markers, must be even)"
    fc=$(grep -cE '^~~~' "$f" || true)
    (( fc % 2 == 0 )) || report_fail "$f" "unclosed tilde fence ($fc markers, must be even)"

    # 7. Heading level jumps (# -> ### without ##)
    awk '
        /^#+ / {
            match($0, /^#+/)
            lvl = RLENGTH
            if (prev > 0 && lvl > prev + 1) {
                printf "  FAIL [%s:%d]: heading jump %d -> %d\n", FILENAME, NR, prev, lvl
                bad = 1
            }
            prev = lvl
        }
        END { if (bad) exit 1; exit 0 }
    ' "$f" || FAIL=1

    # 8-11. Fence-aware structural checks
    awk '
        BEGIN { in_fence = 0; bad = 0; fence_start = 0 }
        /^```/ {
            if (!in_fence) { in_fence = 1; if ($0 ~ /^[ ]+```/) { printf "  FAIL [%s:%d]: code fence with leading whitespace (must start at column 0)\n", FILENAME, NR; bad=1 } }
            else { in_fence = 0 }
            next
        }
        /^~~~ / { next }
        !in_fence {
            if ($0 ~ /^[ ]+#+ /) { printf "  FAIL [%s:%d]: heading with leading whitespace (must start at column 0)\n", FILENAME, NR; bad=1 }
            if ($0 ~ /^     +[-*+] /) { printf "  FAIL [%s:%d]: bullet with 5+ leading spaces (use 0, 2, or 4)\n", FILENAME, NR; bad=1 }
            if ($0 ~ /^     +[0-9]+\. /) { printf "  FAIL [%s:%d]: numbered list with 5+ leading spaces (use 0, 3, or 4)\n", FILENAME, NR; bad=1 }
        }
        END { if (bad) exit 1; exit 0 }
    ' "$f" || FAIL=1

    # 12. WARN: 8+ leading spaces outside code fence (likely over-indent, would render as code block)
    awk '
        /^```/ { in_fence = !in_fence; next }
        !in_fence && /^        [^ ]/ {
            printf "  WARN [%s:%d]: 8+ leading spaces outside code fence (likely over-indent)\n", FILENAME, NR
        }
    ' "$f"

    # 13. WARN: mixed unordered list markers at column 0
    local markers mcount
    markers=$(grep -oE '^[-*+] ' "$f" 2>/dev/null | awk '{print $1}' | sort -u || true)
    mcount=$(printf '%s\n' "$markers" | grep -c . || true)
    if [[ "$mcount" -gt 1 ]]; then
        report_warn "$f" "mixed unordered list markers: $(printf '%s' "$markers" | tr '\n' ' ')"
    fi
}

for f in $FILES; do
    check_file "$f"
done

echo
if [[ $FAIL -eq 0 ]]; then
    echo "[md] PASS"
    exit 0
fi
echo "[md] FAIL"
exit 1
