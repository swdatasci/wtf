# wtf -- What's The Function?

Local-first AI shell line editor augmentation. Type what you want in plain
English, press a keybinding, and get an editable command placed into your
shell's line buffer. Nothing is executed.

## What it does

```
your prompt        wtf does                  you get
-----------        ----------------------    ----------------------------
$ # find large     reads your buffer         sends to local Ollama
  logs             + cwd, shell, git info    <- structured JSON response
                   policy check              <- risk: low
[Ctrl+Space]       buffer replacement        $ find /var/log -type f -size +100M
                                               ^--- edit or press Enter
```

1. Type a natural-language comment or partial command at your normal prompt.
2. Press Ctrl+Space (or Alt+G).
3. wtf sends the buffer plus narrow shell context to a local Ollama model.
4. A deterministic policy layer checks the proposal for dangerous patterns.
5. The safe proposal replaces your line buffer. You can edit it.
6. You press Enter to run it, or Ctrl+C to discard. You are always in control.

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

# Verify available models
ollama list
```

Any Ollama-compatible model works. To use a different model (e.g. one you
already have pulled):

```bash
mkdir -p ~/.config/wtf
cat > ~/.config/wtf/config.toml << 'EOF'
[provider]
model = "gemma4:latest"
EOF
```

Or pass it per-invocation: `wtf propose --model gemma4:latest ...`

## Shell setup

Source the adapter for your shell. The adapters are plain scripts in the
`shell/` directory of this repo.

### Bash

```bash
# Try it now
source /path/to/wtf/shell/wtf.bash

# Make it permanent — add to ~/.bashrc
source /path/to/wtf/shell/wtf.bash
```

### Zsh (also works in fizsh)

```zsh
# Try it now
source /path/to/wtf/shell/wtf.zsh

# Make it permanent — add to ~/.zshrc
source /path/to/wtf/shell/wtf.zsh
```

### Fish

```fish
# Try it now
source /path/to/wtf/shell/wtf.fish

# Make it permanent — add to ~/.config/fish/config.fish
source /path/to/wtf/shell/wtf.fish
```

Replace `/path/to/wtf` with the actual path to this repository.

## Keybindings

| Binding     | Notes                                              |
|-------------|----------------------------------------------------|
| Ctrl+Space  | Primary. Works in most terminals.                  |
| Alt+G       | Fallback for terminals where Ctrl+Space conflicts. |

**tmux users:** Ctrl+Space may collide with the tmux prefix if you rebound it.
Use Alt+G instead.

**NUL byte:** Some terminals send NUL (0x00) for Ctrl+Space. The shell
adapters handle this, but if your terminal swallows it, use Alt+G.

## Usage examples

### Natural language search

```
$ # find all python files modified in the last week
[Ctrl+Space]
$ find . -name "*.py" -mtime -7
```

### Partial command expansion

```
$ tar gz the src directory
[Ctrl+Space]
$ tar czf src.tar.gz src/
```

### Failed command repair

```
$ git push orign main
fatal: 'orign' does not appear to be a git repository

$ # fix that
[Ctrl+Space]
$ git push origin main
```

### Clarification

```
$ # delete something
[Ctrl+Space]
$ # AI needs clarification: delete which files or directories?
```

### Destructive request refusal

```
$ # rm -rf /
[Ctrl+Space]
[wtf] refused: High-risk command: rm
```

## Configuration

Config file: `~/.config/wtf/config.toml`

All fields are optional. Defaults are used for anything not specified.

```toml
[provider]
kind = "ollama"
base_url = "http://127.0.0.1:11434"
model = "qwen2.5-coder:14b"
timeout_seconds = 20

[context]
include_git = true
include_last_command = true
include_last_output = true
max_last_output_bytes = 4096

[policy]
mode = "enforce"                  # "enforce" or "off"
allow_medium_risk_insert = false
max_buffer_bytes = 8192

[ui]
show_summary = true
```

See `examples/sample-config.toml` for a fully commented example.

Environment variables override the config file. Format: `WTF_SECTION_KEY`,
e.g. `WTF_PROVIDER_MODEL=gemma4:latest`.

CLI flags override everything:
`wtf propose --model gemma4:latest --timeout 30 ...`

### Subcommands

```bash
wtf propose --shell bash --cwd . --buffer "# list large files" --cursor 17
wtf doctor                                     # check Ollama, model, Python
wtf config show                                # print resolved config
wtf policy check -- "rm -rf /"                 # show risk level for a command
```

## Security model

1. **Local-only.** All inference runs on your machine via Ollama. No network
   calls leave localhost.

2. **Narrow context.** wtf sends only: your buffer text, current directory,
   shell name, last exit code, and (optionally) the last command and git
   metadata. No env vars, no secrets, no file contents.

3. **No auto-execution.** Proposals are placed into the line buffer.
   You must press Enter to run them.

4. **Deterministic policy layer.** After the model proposes a command, a
   rule-based policy engine evaluates it independent of the model:
   - **low** risk -- inserted into the line buffer.
   - **medium** risk -- refused by default (enable with
     `allow_medium_risk_insert = true`).
   - **high** risk -- always refused, never reaches the line buffer.

   The policy layer is deterministic and cannot be prompt-injected.

## Troubleshooting

### wtf doctor

Run `wtf doctor` to check your setup:

```
$ wtf doctor
[ok] Python version: 3.13.5
[ok] Ollama: Ollama is reachable
[ok] Model 'gemma4:latest' is available
[ok] JSON generation test passed
```

### Common issues

**"Connection refused" on propose**
Ollama is not running. Start it with `ollama serve`.

**"Model not found"**
Pull the model: `ollama pull qwen2.5-coder:14b` (or your configured model).
Check what you have: `ollama list`.

**Ctrl+Space does nothing**
- Verify shell adapter is sourced: `source /path/to/shell/wtf.bash`
- Try Alt+G as a fallback.
- In tmux, check for prefix key conflicts.

**Proposals are slow**
The default model (qwen2.5-coder:14b) needs ~10GB VRAM. If running on CPU,
try a smaller model: `qwen2.5-coder:7b` or `qwen2.5-coder:3b`.

**Policy refuses a legitimate command**
Check what triggered it: `wtf policy check -- "your command here"`.
Enable medium-risk insertion in config if needed.

## Dogfood checklist

- [ ] Shell adapter sources without errors in bash, zsh, fish
- [ ] Type `# question`, then Ctrl+Space produces a reasonable command
- [ ] Proposed command lands in the line buffer, cursor ready to edit
- [ ] `rm -rf /` is refused (risk: high)
- [ ] `ls -la` is inserted cleanly (risk: low)
- [ ] `wtf doctor` reports all-clear on a working setup
- [ ] `wtf propose` works as a one-shot CLI tool (no shell integration needed)
- [ ] Works with no config file (defaults apply)

## License

MIT
