#!/usr/bin/env bash
# wtf.bash — Bash adapter for wtf (What's The Function?)
# Source this file in .bashrc:  source /path/to/wtf.bash
#
# Binds Ctrl+Space and Alt+g to propose AI-generated commands via Ollama.
# Never executes anything — only proposes.

# ---------- last-command capture ----------

# Must run FIRST in PROMPT_COMMAND to capture $? before other hooks clobber it.
_wtf_capture_last() {
    _wtf_last_exit=$?
    local hist
    hist=$(HISTTIMEFORMAT='' history 1)
    # Strip leading history number + whitespace
    _wtf_last_cmd="${hist#*[0-9] }"
}

# Prepend our capture to PROMPT_COMMAND without disrupting existing hooks.
if [[ -z "$PROMPT_COMMAND" ]]; then
    PROMPT_COMMAND='_wtf_capture_last'
elif [[ "$PROMPT_COMMAND" != *'_wtf_capture_last'* ]]; then
    PROMPT_COMMAND="_wtf_capture_last;${PROMPT_COMMAND}"
fi

# ---------- proposal function ----------

_wtf_bash_propose() {
    # Bail early if wtf is not installed
    if ! command -v wtf &>/dev/null; then
        echo -e "\n[wtf] command not found — install with: pip install wtf" >&2
        return
    fi

    local buffer="$READLINE_LINE"
    local cursor="$READLINE_POINT"
    local args=()

    args+=(propose --shell bash --cwd "$PWD" --buffer "$buffer" --cursor "$cursor")
    args+=(--format shell)

    # Optional git context
    if git rev-parse --is-inside-work-tree &>/dev/null 2>&1; then
        local branch
        branch=$(git symbolic-ref --short HEAD 2>/dev/null || git rev-parse --short HEAD 2>/dev/null)
        if [[ -n "$branch" ]]; then
            args+=(--git-branch "$branch")
        fi
        local dirty=""
        if ! git diff --quiet HEAD 2>/dev/null; then
            dirty="true"
        fi
        if [[ -n "$dirty" ]]; then
            args+=(--git-dirty)
        fi
    fi

    # Optional last-command context
    if [[ -n "${_wtf_last_cmd:-}" ]]; then
        args+=(--last-cmd "$_wtf_last_cmd" --last-exit "${_wtf_last_exit:-0}")
    fi

    # Call wtf and capture output
    local output
    output=$(wtf "${args[@]}" 2>/dev/null)
    local rc=$?

    if [[ $rc -ne 0 ]]; then
        echo -e "\n[wtf] propose failed (exit $rc)" >&2
        return
    fi

    # --format shell outputs variable assignments:
    #   WTF_ACTION=replace_buffer|ask|refuse|error
    #   WTF_BUFFER="..."
    #   WTF_CURSOR=N
    #   WTF_MESSAGE="..."
    local WTF_ACTION="" WTF_BUFFER="" WTF_CURSOR="" WTF_MESSAGE=""
    eval "$output"

    case "$WTF_ACTION" in
        replace_buffer)
            READLINE_LINE="$WTF_BUFFER"
            READLINE_POINT="${WTF_CURSOR:-${#WTF_BUFFER}}"
            ;;
        ask)
            READLINE_LINE="$WTF_BUFFER"
            READLINE_POINT="${WTF_CURSOR:-${#WTF_BUFFER}}"
            ;;
        refuse)
            echo -e "\n[wtf] refused: ${WTF_MESSAGE:-policy violation}" >&2
            ;;
        error)
            echo -e "\n[wtf] error: ${WTF_MESSAGE:-unknown error}" >&2
            ;;
        *)
            echo -e "\n[wtf] unexpected action: $WTF_ACTION" >&2
            ;;
    esac
}

# ---------- key bindings ----------

# Ctrl+Space (sends NUL / Ctrl+@)
bind -x '"\C-@":_wtf_bash_propose'

# Alt+g fallback
bind -x '"\eg":_wtf_bash_propose'
