# Installing HCL MCP

`hcl-mcp` is a local, human-centric-lighting MCP server: spectral sky reconstruction from EPW,
α-opic / melanopic metrics, circadian compliance, Radiance daylight simulation, electric-lighting
and glare tools — exposed to any MCP client that speaks **stdio**.

This manual covers **macOS, Windows, and Linux** and five clients: **Claude Code, Claude Desktop,
Gemini CLI, Antigravity, and VS Code**.

> **You need two things:** (1) **`uv`** — the Python launcher that installs and runs the server
> (Step 1); (2) *optionally* **Radiance** — a separate, free engine for live daylight simulation
> (Step 1, optional). Installing the server takes one command (Step 2).

---

## Fastest route — Claude Code plugin (two lines)

If your client is **Claude Code**, skip Steps 2 and 3. Install `uv` (Step 1a), then run:

```
/plugin marketplace add akontadakis/hcl-mcp
/plugin install hcl-mcp@hcl-mcp
```

Restart Claude Code and verify with `/mcp`. This registers the server *and* the
`running-hcl-studies` skill. Radiance is still optional (Step 1b); the plugin passes no
environment variables, so set `HCL_RADIANCE_BIN` / `RAYPATH` in your shell profile if you
need live simulation. Every other client, and the `--env` route, continues below.

---

## What works with vs. without Radiance

The server installs and runs on its own. Radiance is only needed for *live ray-traced* results.

| Capability | Needs Radiance? |
|---|---|
| Spectral sky from EPW, α-opic / melanopic / circadian metrics, spectral reconstruction, compliance (WELL / EN 17037 / ISO-CIE), IES photometry, briefs & presets | **No** — pure Python, works everywhere immediately |
| **Emit mode** — every Radiance tool returns the *exact commands* to run yourself | **No** — always available |
| **Live** grid / annual / image / electric simulation (`run_grid`, `run_annual`, `run_image`, …) | **Yes** — install Radiance (below) |
| `annual_nvrd` enhanced reconstruction (Daysim) | **Yes** for the live path — **Daysim not verified cross-platform** (experimental); see the note in Step 1 |

If Radiance is absent, live tools don't error — they report `available: false` and emit the commands.

---

## Step 1 — Prerequisites

### 1a. Install `uv` (required)

`uv` is a single static binary; no Python setup needed.

**macOS / Linux**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
*(or `brew install uv` on macOS)*

**Windows** (PowerShell)
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
*(or `winget install astral-sh.uv`)*

Then restart your terminal and confirm:
```bash
uv --version
```

### 1b. Install Radiance (optional — for live simulation)

Radiance is a separate, free, open-source engine (LBNL). Download the latest release for your OS
from the official releases (**github.com/LBNL-ETA/Radiance/releases** or **radiance-online.org**).
**Minimum tested: Radiance 5.4** (also verified on 6.1a). Nothing is bundled with `hcl-mcp`.

> **→ For the full engine checklist — Radiance **and** Daysim **and** SMARTS, each with get-source →
> build → set-env → verify steps — follow [`docs/engines-install.md`](docs/engines-install.md).** It is
> written to be executed top-to-bottom.


After installing, do **one** of:

- **Add Radiance's `bin` to your `PATH`** (the installer usually offers this), **or**
- **Point `HCL_RADIANCE_BIN`** at the Radiance `bin` directory (set it in your client config, Step 3).

For annual / `.cal`-based workflows Radiance also needs **`RAYPATH`** set to its `lib` directory —
the official installers set this for you.

> **Daysim (experimental / not verified cross-platform).** The `annual_nvrd` enhanced path uses
> Daysim, which is **not verified on any OS other than the dev machine** — `build_daysim`'s own
> clone+build path is emit/unit-tested only, and the opt-in `physical_sky` flip is not live-validated.
> The enhanced colored-sun is **time-resolved on a successful Daysim run** (`generate_subhourly_wea`
> surfaces per-timestep solar zeniths, which `annual_nvrd` feeds into the reconstruction); a constant
> **30°** zenith is used only in degraded mode (no Daysim / empty `.wea`) and is labelled in the
> output's `enhanced_solar_note`. On macOS/Linux you can build Daysim with the `build_daysim` tool; on
> Windows point `HCL_DAYSIM_BIN` at a Daysim install. Treat its output as experimental.

---

## Step 2 — Install the server (choose one method)

### Method A — One-line install (recommended)

No clone, no setup. Your MCP client launches the server directly with this command, and `uv` fetches,
builds, and caches it on first run:

```bash
uvx --from git+https://github.com/akontadakis/hcl-mcp hcl-mcp
```

Pin a specific release or commit by appending `@<ref>` — any tag, branch, or commit SHA the
repository carries. For example, the `v0.1.1` release:

```bash
uvx --from git+https://github.com/akontadakis/hcl-mcp@v0.1.1 hcl-mcp
```

> **Releases are tagged from `v0.1.1` on.** `v0.1.1` is the first release with the corrected
> LM-83 engine; an `lm83_daylight` result from an earlier state is far too low and must not be
> used. Omit the `@<ref>` to take the default branch, or pin a tag or an exact commit SHA when a
> result has to be reproducible.

You normally never type this yourself — you paste it into a client config in Step 3. To sanity-check
it once by hand, run the command above; it should start and wait on stdio (Ctrl-C to exit).

### Method B — Manual clone + install (fallback)

If you'd rather have a local checkout, or `uvx` isn't an option:

```bash
git clone https://github.com/akontadakis/hcl-mcp.git
cd hcl-mcp
uv tool install .
```

This installs `hcl-mcp` as a command on your `PATH`. To update later:

```bash
git pull
uv tool install . --reinstall
```

> **Do not** launch the server with `uv run --directory …` from the clone — that path relies on an
> editable install that is unreliable here. Use `uv tool install .` (above), which installs the
> package properly and needs no `PYTHONPATH`.

**With Method B, the launch command is simply `hcl-mcp`** (no `uvx` wrapper). In every Step-3 config
below, replace:

```jsonc
"command": "uvx",
"args": ["--from", "git+https://github.com/akontadakis/hcl-mcp", "hcl-mcp"]
```

with:

```jsonc
"command": "hcl-mcp",
"args": []
```

---

### Method C — Claude Code plugin (Claude Code only)

This repository doubles as a Claude Code plugin marketplace: `.claude-plugin/marketplace.json`
lists one plugin, and the repo-root `.mcp.json` declares the server. Installing it does Step 2
*and* Step 3 in one go.

```
/plugin marketplace add akontadakis/hcl-mcp
/plugin install hcl-mcp@hcl-mcp
```

Restart Claude Code, then run `/mcp` — `hcl-mcp` should be listed and connected.

Under the hood the plugin runs exactly the Method A command
(`uvx --from git+https://github.com/akontadakis/hcl-mcp hcl-mcp`), so `uv` must be on your
`PATH`. Two consequences:

- **No `env` block.** The server inherits the environment Claude Code was started with. Put
  `HCL_RADIANCE_BIN`, `RAYPATH`, `SMARTSPATH`, `HCL_DAYSIM_BIN` and `HCL_WORK_ROOT` in your
  shell profile (`~/.zshrc`, `~/.bashrc`) or use Method A + Step 3 instead, which accepts `--env`.
- **The plugin clone is not the running code.** `uvx` fetches its own copy from GitHub. Run
  `/plugin` to update the plugin, and it picks up the new `.mcp.json`; the server itself
  re-resolves from the default branch on the next `uvx` cache miss.

Manage or remove it later from `/plugin`.

---

## Step 3 — Register with your client

Where each client keeps its config:

| Client | Config location | Top-level key |
|---|---|---|
| Claude Code | `claude mcp add …` (CLI, no file editing) | — |
| Claude Desktop | macOS: `~/Library/Application Support/Claude/claude_desktop_config.json` · Windows: `%APPDATA%\Claude\claude_desktop_config.json` | `mcpServers` |
| Gemini CLI | `~/.gemini/settings.json` | `mcpServers` |
| Antigravity | UI: **… → MCP Servers → Manage MCP Servers → View raw config** (file: `~/.gemini/config/mcp_config.json`) | `mcpServers` |
| VS Code | `.vscode/mcp.json` (workspace) or user `mcp.json` | `servers` |

The blocks below use **Method A** (`uvx`). For Method B, apply the `command`/`args` swap from Step 2.
Any `HCL_*` environment variable (Radiance path, work dir) goes in the `env` object — omit it if
Radiance is on your `PATH`.

### Claude Code

```bash
claude mcp add hcl-mcp -- uvx --from git+https://github.com/akontadakis/hcl-mcp hcl-mcp
```

Add environment variables with `--env` (repeatable), e.g. to point at a Radiance install:

```bash
claude mcp add hcl-mcp \
  --env HCL_RADIANCE_BIN=/usr/local/radiance/bin \
  -- uvx --from git+https://github.com/akontadakis/hcl-mcp hcl-mcp
```

Use `-s user` to register it globally instead of for the current project. Verify with `claude mcp list`.

### Claude Desktop (macOS / Windows)

Edit `claude_desktop_config.json` (path in the table above), add the block, and **restart Claude
Desktop**:

```json
{
  "mcpServers": {
    "hcl-mcp": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/akontadakis/hcl-mcp", "hcl-mcp"],
      "env": {
        "HCL_RADIANCE_BIN": "/usr/local/radiance/bin"
      }
    }
  }
}
```

> Claude Desktop has no official Linux build — on Linux use Claude Code, Gemini CLI, Antigravity, or
> VS Code instead.

### Gemini CLI

Add the same `mcpServers` block to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "hcl-mcp": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/akontadakis/hcl-mcp", "hcl-mcp"]
    }
  }
}
```

Restart Gemini CLI; run `/mcp` to confirm the server and its tools loaded.

### Antigravity

In the editor's agent side panel, click **…** → **MCP Servers** → **Manage MCP Servers** →
**View raw config**, then add the same `mcpServers` block:

```json
{
  "mcpServers": {
    "hcl-mcp": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/akontadakis/hcl-mcp", "hcl-mcp"]
    }
  }
}
```

Save, then hit **refresh** in the Installed MCP Servers section.

### VS Code

VS Code uses `servers` (not `mcpServers`) and requires `"type": "stdio"`. Create `.vscode/mcp.json`
in your workspace:

```json
{
  "servers": {
    "hcl-mcp": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/akontadakis/hcl-mcp", "hcl-mcp"]
    }
  }
}
```

Or add it from the command line:

```bash
code --add-mcp '{"name":"hcl-mcp","type":"stdio","command":"uvx","args":["--from","git+https://github.com/akontadakis/hcl-mcp","hcl-mcp"]}'
```

Open the **MCP: List Servers** command to start it and confirm the tools appear in Agent mode.

---

## Step 4 — Verify it works

In any client:

1. Confirm the **hcl-mcp** tools appear in the tool list.
2. Call a **pure-Python** tool that never needs Radiance, e.g. `list_presets` or `get_reference`.
3. Call **`radiance_status`** — it reports `{available, bin_dir, version, found, missing}`. `available:
   true` means live simulation is ready; `false` is fine and expected if you skipped Step 1b.
4. If you installed any engine, run the checks in
   [`docs/engines-install.md`](docs/engines-install.md) **Step 4** — including
   `radiance_status().source_cal.a1_honored`, which must not be `false`.

---

## Environment variables (reference)

Set these in your client config's `env` block (or your shell) as needed:

| Variable | Purpose | Example |
|---|---|---|
| `HCL_RADIANCE_BIN` | Radiance `bin` dir, if not on `PATH` | `/usr/local/radiance/bin` · `C:/Radiance/bin` |
| `HCL_DAYSIM_BIN` | Daysim `bin` dir (experimental) | `/usr/local/daysim/bin` |
| `HCL_DAYSIM_REF` | Daysim commit or branch for `build_daysim`, in place of the pinned commit | unset |
| `HCL_WORK_ROOT` | Where the server writes scenes/results | `~/hcl-work` |
| `HCL_ATMOS_CACHE` | Where `gensdaymtx` keeps its pre-computed scattering tables (`atmos_data/`). The first run fills it (minutes; tens of MB to a few GB, by how many atmosphere states the weather file spans); later runs reuse it | `<HCL_WORK_ROOT>/atmos_cache` |
| `RAYPATH` | Radiance `lib` dir (required for annual runs). For `gensdaymtx` the server finds the `lib` beside `bin` by itself when this is unset | `.:/usr/local/radiance/lib` |
| `SMARTSPATH` | The `smarts295bat` **executable file**, not its directory | `~/smarts/smarts295bat` |

> **Windows + JSON:** use forward slashes (`C:/Radiance/bin`) or escaped backslashes
> (`C:\\Radiance\\bin`) inside `.json` files.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `uvx: command not found` | `uv` isn't installed or not on `PATH` — redo Step 1a and restart the terminal. |
| Method B: `hcl-mcp: command not found` | Run `uv tool update-shell` (adds uv's tool bin dir to `PATH`), then restart the terminal. |
| Radiance tools show `available: false` | Radiance isn't found — install it (Step 1b) and set `HCL_RADIANCE_BIN`, or add its `bin` to `PATH`. |
| Annual runs fail with missing `.cal` | Set `RAYPATH` to Radiance's `lib` directory. |
| Client shows no tools after editing JSON | Restart the client; check the JSON is valid (no trailing commas) and uses the right top-level key (`servers` for VS Code, `mcpServers` for the rest). |
| First launch is slow | `uvx` builds and caches the package on first run; later launches are fast. |

---

## Updating & uninstalling

- **Method A (`uvx`):** pin a tag (`@v0.1.1`) for a fixed version, or omit it to track the latest on
  each new launch. Clear the cache with `uv cache clean` to force a rebuild.
- **Method B (`uv tool install`):** `git pull && uv tool install . --reinstall` to update;
  `uv tool uninstall hcl-mcp` to remove.
