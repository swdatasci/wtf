#!/usr/bin/env fish
# wtf.fish — Fish adapter for wtf (What's The Function?)
# Source this file in config.fish:  source /path/to/wtf.fish
#
# Binds Ctrl+Space and Alt+g to propose AI-generated commands via Ollama.
# Never executes anything — only proposes.

# ---------- last-command capture ----------

set -g _wtf_last_cmd ""
set -g _wtf_last_exit 0

function _wtf_fish_preexec --on-event fish_preexec
    set -g _wtf_last_cmd $argv[1]
end

function _wtf_fish_postexec --on-event fish_postexec
    set -g _wtf_last_exit $status
end

# ---------- proposal function ----------

function _wtf_fish_propose
    # Bail early if wtf is not installed
    if not command -q wtf
        echo "[wtf] command not found — install with: pip install wtf" >&2
        commandline -f repaint
        return
    end

    set -l buffer (commandline --current-buffer)
    set -l cursor (commandline --cursor)
    set -l args propose --shell fish --cwd $PWD --buffer "$buffer" --cursor $cursor
    set -a args --format shell

    # Optional git context
    if git rev-parse --is-inside-work-tree >/dev/null 2>&1
        set -l branch (git symbolic-ref --short HEAD 2>/dev/null; or git rev-parse --short HEAD 2>/dev/null)
        if test -n "$branch"
            set -a args --git-branch $branch
        end
        if not git diff --quiet HEAD 2>/dev/null
            set -a args --git-dirty
        end
    end

    # Optional last-command context
    if test -n "$_wtf_last_cmd"
        set -a args --last-command "$_wtf_last_cmd" --last-exit-code $_wtf_last_exit
    end

    # Call wtf and capture output
    set -l output (wtf $args 2>/dev/null)
    set -l rc $status

    if test $rc -ne 0
        echo "[wtf] propose failed (exit $rc)" >&2
        commandline -f repaint
        return
    end

    # Parse shell variable assignments from --format shell output.
    # Fish can't eval bash-style assignments, so we parse line by line.
    set -l WTF_ACTION ""
    set -l WTF_BUFFER ""
    set -l WTF_CURSOR ""
    set -l WTF_MESSAGE ""

    for line in $output
        switch $line
            case 'WTF_ACTION=*'
                set WTF_ACTION (string replace 'WTF_ACTION=' '' -- $line | string trim --chars='"\'')
            case 'WTF_BUFFER=*'
                set WTF_BUFFER (string replace 'WTF_BUFFER=' '' -- $line | string trim --chars='"\'')
            case 'WTF_CURSOR=*'
                set WTF_CURSOR (string replace 'WTF_CURSOR=' '' -- $line | string trim --chars='"\'')
            case 'WTF_MESSAGE=*'
                set WTF_MESSAGE (string replace 'WTF_MESSAGE=' '' -- $line | string trim --chars='"\'')
        end
    end

    switch $WTF_ACTION
        case replace_buffer
            commandline --replace -- "$WTF_BUFFER"
            if test -n "$WTF_CURSOR"
                commandline --cursor $WTF_CURSOR
            end
        case ask
            commandline --replace -- "$WTF_BUFFER"
            if test -n "$WTF_CURSOR"
                commandline --cursor $WTF_CURSOR
            end
        case refuse
            echo "[wtf] refused: $WTF_MESSAGE" >&2
        case error
            echo "[wtf] error: $WTF_MESSAGE" >&2
        case '*'
            echo "[wtf] unexpected action: $WTF_ACTION" >&2
    end

    commandline -f repaint
end

# ---------- key bindings ----------

# Ctrl+Space (sends NUL / Ctrl+@)
bind \c@ _wtf_fish_propose

# Alt+g fallback
bind \eg _wtf_fish_propose
