# wtf -- What's The Function?

Local-first AI shell line editor augmentation. Ask what you want in plain
English, get an editable command placed into your shell's line buffer.
Nothing is executed.

## What it does

```
You type          wtf sees                  You get
-----------       ----------------------    ----------------------------
Ctrl+Space        prompt opens              "find large logs"
                  Ollama (local, private)   -> proposal
                  policy check              -> risk: low
                  line buffer insert        $ find /var/log -type f -size +100M
                                              ^--- cursor here, edit or Enter
```

1. You press the keybinding (Ctrl+Space).
2. You type natural language or a partial command.
3. `wtf` sends your input plus narrow shell context to a local Ollama model.
4. A deterministic policy layer checks the proposal for dangerous patterns.
5. The safe proposal is placed into your shell's line buffer for review.
6. You edit or press Enter. You are always in control.

## What it does NOT do

- It is not a shell. It augments your existing shell.
- It is not an agent. It proposes one command at a time.
- It never executes commands. Proposals go into the line buffer only.
- It never sends data off your machine. Ollama runs locally.
- It does not replace your shell history, aliases, or muscle memory.

## Installation

Requires Python 3.11+ and a running Ollama instance.

```bash
# With uv (recommended)
uv tool install /path/to/wtf

# With pipx
pipx install /path/to/wtf

# Development install
uv pip install -e /path/to/wtf
```

No third-party runtime dependencies. Stdlib only.

## Ollama setup

wtf talks to Ollama on `http://127.0.0.1:11434` by default.

```bash
# Start the server (if not already running)
ollama serve

# Pull the default model
ollama pull qwen2.5-coder:14b

# Verify
ollama list
```

Any Ollama-compatible model works. Change the model in config (see below).

## Shell setup

### Bash

Add to `~/.bashrc`:

```bash
source "$(wtf shell bash)"
```

### Zsh

Add to `~/.zshrc`:

```zsh
source "$(wtf shell zsh)"
```

### Fish

Add to `~/.config/fish/config.fish`:

```fish
wtf shell fish | source
```

Restart your shell or source the rc file after adding the line.

## Keybindings

| Binding     | Notes                                              |
|-------------|----------------------------------------------------|
| Ctrl+Space  | Primary. Works in most terminals.                  |
| Alt+G       | Fallback for terminals where Ctrl+Space conflicts. |

**tmux users:** Ctrl+Space may collide with the tmux prefix if you rebound it.
Use Alt+G or rebind in your wtf config.

**NUL byte:** Some terminals send NUL (0x00) for Ctrl+Space. The shell
integration handles this, but if your terminal swallows it, use Alt+G.

## Usage examples

### Natural language search

```
[Ctrl+Space] find all python files modified in the last week
$ find . -name "*.py" -mtime -7
```

### Partial command expansion

```
[Ctrl+Space] tar gz the src directory
$ tar czf src.tar.gz src/
```

### Failed command repair

```
$ git push orign main
fatal: 'orign' does not appear to be a git repository

[Ctrl+Space] fix that
$ git push origin main
```

### Clarification

```
[Ctrl+Space] delete everything
wtf: refused (risk: high) -- mass deletion without explicit path
```

### Destructive request refusal

```
[Ctrl+Space] rm -rf /
wtf: refused (risk: high) -- recursive root deletion
```

## Configuration

Config file: `~/.config/wtf/config.toml`

Created on first run with defaults. All fields are optional.

```toml
[ollama]
url = "http://127.0.0.1:11434"
model = "qwen2.5-coder:14b"
timeout = 10                     # seconds

[context]
include_cwd = true
include_last_exit = true
include_last_command = true
max_history = 0                  # number of recent commands to include (0 = none)

[policy]
allow_sudo = false               # if false, proposals with sudo are risk: medium
refuse_rm_rf = true              # hard-refuse recursive root deletion
max_risk = "medium"              # "low", "medium", "high" -- ceiling for insertion

[keybinding]
primary = "\\C-@"                # Ctrl+Space
fallback = "\\eg"                # Alt+G
```

### Subcommands

```bash
wtf propose "list disk usage by directory"   # one-shot, print to stdout
wtf doctor                                    # check Ollama, model, shell integration
wtf config show                               # print resolved config
wtf policy check "rm -rf /"                   # show risk level for a command
```

## Security model

1. **Local-only.** All inference runs on your machine via Ollama. No network
   calls leave localhost.

2. **Narrow context.** wtf sends only: your prompt, current directory,
   last exit code, and (optionally) the last command. No env vars, no
   secrets, no file contents.

3. **No secrets in transit.** The Ollama connection is localhost HTTP.
   No API keys are used or stored.

4. **No auto-execution.** Proposals are placed into the line buffer.
   You must press Enter to run them.

5. **Deterministic policy layer.** After the model proposes a command, a
   rule-based policy engine evaluates it:
   - **low** -- safe to insert into the line buffer.
   - **medium** -- inserted with a warning comment prepended.
   - **high** -- refused entirely, never reaches the line buffer.

   The policy layer is deterministic and does not depend on the model.
   It cannot be prompt-injected.

## Troubleshooting

### wtf doctor

Run `wtf doctor` to check your setup. It verifies:

- Ollama is reachable at the configured URL
- The configured model is pulled and available
- Shell integration is sourced in the current shell
- Config file parses without errors

### Common issues

**"Connection refused" on propose**
Ollama is not running. Start it with `ollama serve`.

**"Model not found"**
Pull the model: `ollama pull qwen2.5-coder:14b` (or your configured model).

**Ctrl+Space does nothing**
- Verify shell integration is sourced: check your rc file.
- Try Alt+G as a fallback.
- In tmux, check for prefix key conflicts.
- Run `wtf doctor` to confirm integration is loaded.

**Proposals are slow**
The default model (qwen2.5-coder:14b) needs ~10GB VRAM. If you're running on
CPU, try a smaller model: `qwen2.5-coder:7b` or `qwen2.5-coder:3b`.

**Policy refuses a legitimate command**
Check the risk ceiling in config (`policy.max_risk`). Run
`wtf policy check "<command>"` to see why it was flagged.

## Dogfood checklist

- [ ] Ctrl+Space opens the prompt in bash, zsh, fish
- [ ] Natural language input produces a reasonable command
- [ ] Proposed command lands in the line buffer, cursor ready to edit
- [ ] `rm -rf /` is refused (risk: high)
- [ ] `sudo rm -rf /tmp/junk` is flagged (risk: medium with allow_sudo=false)
- [ ] `ls -la` is inserted cleanly (risk: low)
- [ ] `wtf doctor` reports all-clear on a working setup
- [ ] `wtf propose` works as a one-shot CLI tool (no shell integration needed)
- [ ] Config changes take effect without restart
- [ ] Works with no config file (defaults apply)

## License

MIT
