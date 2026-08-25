#!/usr/bin/env zsh
# wtf.zsh — Zsh adapter for wtf (What's The Function?)
# Source this file in .zshrc:  source /path/to/wtf.zsh
#
# Binds Ctrl+Space and Alt+g to propose AI-generated commands via Ollama.
# Never executes anything — only proposes.

# ---------- last-command capture ----------

typeset -g _wtf_last_cmd=""
typeset -g _wtf_last_exit=0

_wtf_preexec() {
    _wtf_last_cmd="$1"
}

_wtf_precmd() {
    _wtf_last_exit=$?
}

# Register hooks without duplicating
autoload -Uz add-zsh-hook
add-zsh-hook preexec _wtf_preexec
add-zsh-hook precmd  _wtf_precmd

# ---------- ZLE widget ----------

wtf-zsh-propose() {
    # Bail early if wtf is not installed
    if ! (( $+commands[wtf] )); then
        zle -M "[wtf] command not found — install with: pip install wtf"
        return
    fi

    local buffer="$BUFFER"
    local cursor="$CURSOR"
    local -a args

    args=(propose --shell zsh --cwd "$PWD" --buffer "$buffer" --cursor "$cursor")
    args+=(--format shell)

    # Optional git context
    if git rev-parse --is-inside-work-tree &>/dev/null 2>&1; then
        local branch
        branch=$(git symbolic-ref --short HEAD 2>/dev/null || git rev-parse --short HEAD 2>/dev/null)
        if [[ -n "$branch" ]]; then
            args+=(--git-branch "$branch")
        fi
        if ! git diff --quiet HEAD 2>/dev/null; then
            args+=(--git-dirty)
        fi
    fi

    # Optional last-command context
    if [[ -n "$_wtf_last_cmd" ]]; then
        args+=(--last-command "$_wtf_last_cmd" --last-exit-code "$_wtf_last_exit")
    fi

    # Call wtf and capture output
    local output
    output=$(wtf "${args[@]}" 2>/dev/null)
    local rc=$?

    if [[ $rc -ne 0 ]]; then
        zle -M "[wtf] propose failed (exit $rc)"
        return
    fi

    # Parse shell variable assignments from --format shell output
    local WTF_ACTION="" WTF_BUFFER="" WTF_CURSOR="" WTF_MESSAGE=""
    eval "$output"

    case "$WTF_ACTION" in
        replace_buffer)
            BUFFER="$WTF_BUFFER"
            CURSOR="${WTF_CURSOR:-${#BUFFER}}"
            zle redisplay
            ;;
        ask)
            BUFFER="$WTF_BUFFER"
            CURSOR="${WTF_CURSOR:-${#BUFFER}}"
            zle redisplay
            ;;
        refuse)
            zle -M "[wtf] refused: ${WTF_MESSAGE:-policy violation}"
            ;;
        error)
            zle -M "[wtf] error: ${WTF_MESSAGE:-unknown error}"
            ;;
        *)
            zle -M "[wtf] unexpected action: $WTF_ACTION"
            ;;
    esac
}

zle -N wtf-zsh-propose

# ---------- key bindings ----------

# Ctrl+Space (sends Ctrl+@)
bindkey '^@' wtf-zsh-propose

# Alt+g fallback
bindkey '^[g' wtf-zsh-propose
