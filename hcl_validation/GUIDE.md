# hcl-mcp — Complete Beginner's Guide

This guide assumes you have **never used an MCP server before** and aren't sure what any of
this is. Read it top to bottom the first time. Every step tells you exactly what to type and
what you should see. When a word looks like jargon, it's explained the first time it appears.

By the end you'll be able to:

1. Connect the lighting toolbox to your AI assistant — **Claude Code**, **Gemini CLI**, or
   **Google Antigravity** (one-time setup).
2. Check that it actually connected.
3. Have your assistant auto-test the whole thing for you.
4. Swap in **your own** building, weather, light fixture, or spectrum files.
5. Drive it yourself, in detail, using every prompt, tool, and resource it offers.

> **A note on wording.** This guide works with any MCP-capable AI assistant. Throughout, it says
> "**the assistant**" for the generic actor, and shows concrete examples in **Claude Code's**
> spelling (e.g. the `/mcp__hcl-mcp__…` slash commands and the `/mcp` health check), because that's the most verbose form. Where another client differs, it's called out inline — and the one-time *connect* step has its own per-client section ([Part 1](#part-1--one-time-setup-claude-code) for Claude Code, [Part 1B](#part-1b--connect-to-gemini-cli-or-antigravity) for Gemini CLI and Antigravity). Everything else is identical across clients.

---

# PART 0 — What is this thing? (read once, 3 minutes)

### The plain-language version

You have an **AI assistant** that speaks MCP — for example **Claude Code**, **Gemini CLI**, or
**Google Antigravity** (the app you're typing into right now). Any of them works; the toolbox is
the same.

By itself, the assistant can talk but can't *do* lighting science. This project adds a **toolbox**
the assistant can pick up and use. The toolbox is called **hcl-mcp**. "HCL" = *Human-Centric
Lighting* (designing light around how it affects people — alertness, the body clock, comfort —
not just brightness). Once connected, the assistant can call ~45 lighting tools: analyze a light
spectrum, import a 3D model of a room, simulate daylight, render an eye-level glare image,
estimate energy savings, and more.

A few terms you'll keep seeing:

| Term               | What it means in plain English                                                                                                                                                                                                                                                                                                                                             |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **MCP**      | "Model Context Protocol." Just a standard way to plug a toolbox into an AI assistant. You don't need to understand the protocol — only that it's how the assistant reaches the tools. It's an open standard, which is why the same server works in Claude Code, Gemini CLI, and Antigravity.                                                                              |
| **server**   | The background program that holds the tools. It starts automatically; you never run it by hand.                                                                                                                                                                                                                                                                            |
| **tool**     | One action the assistant can take, e.g. "analyze this spectrum." There are 50 entries (46 unique + 4 nicknames).                                                                                                                                                                                                                                                           |
| **prompt**   | A pre-written, guided workflow you trigger by typing a slash command (like`/something`). It chains several tools for you. There are 13.                                                                                                                                                                                                                                  |
| **resource** | A reference document the tool can read on demand (lookup tables, glossaries, presets). There are 14.                                                                                                                                                                                                                                                                       |
| **engine**   | An external physics program the tools call for heavy simulation:**Radiance** (light simulation), **Daysim** (year-long daylight), **SMARTS** (sky spectrum). All **optional** — if installed the sim tools run live, else they emit a command plan (still valid). Install: [Appendix A](#a--installing-the-engines-optional--for-live-simulation). |

### The mental model

```
You  ──type──▶  AI assistant  ──calls──▶  hcl-mcp toolbox (the "server")
   (Claude Code /
    Gemini CLI /
    Antigravity)
                                              │
                                              ├─ light-math tools  (work instantly, no files)
                                              └─ simulation tools  ──run──▶  Radiance / Daysim / SMARTS
```

### Three important facts that prevent 90% of confusion

1. **Some tools need files, some don't.** The pure math tools (spectrum → circadian numbers)
   need nothing but a few numbers you paste in. The simulation tools need real files: a 3D
   room (`.obj`), a weather file (`.epw`), a light fixture (`.ies`), etc. Ready-made example
   files already ship in the [`inputs/`](inputs/) folder, so you can run everything before ever supplying your own.
2. **"Didn't run" is sometimes the correct answer.** If a simulation engine isn't installed,
   a tool returns a *plan* of the commands it **would** run (`"ran": false` plus a `commands[]`
   list), instead of an error. That's intentional and counts as a pass. On *this* machine all
   engines are installed, so tools run for real.
3. **A result can come with a warning attached — read it before you quote the number.** Many
   results carry an `advisories` list: short notes the tool adds about *how to read its own
   output*. They are **not** errors and **not** failures — the number is still there. Three
   severities: `error` (probably not usable as-is), `warn` (usable but easy to misreport), `info`
   (a default was applied — confirm it's the one you wanted). When nothing needs saying, the key
   simply isn't there, so if you see it, it's worth ten seconds. Some are expected on the example
   files — e.g. the shipped Athens weather file records a ground reflectance of literally `0.000`,
   which isn't physical, so the toolkit substitutes a sensible default and tells you it did
   (`ALBEDO_NOT_MEASURED`). That's the system being honest, not broken.

You don't need to memorize any of this. It'll make sense as you go.

---

# PART 1 — One-time setup (Claude Code)

You do this **once**. After that it reconnects automatically every time you open the app.

> **Which client are you using?**
>
> - **Claude Code** → this part (Part 1).
> - **Gemini CLI or Google Antigravity** → [Part 1B](#part-1b--connect-to-gemini-cli-or-antigravity).
>
> **Step 1.1 below (`uv sync`) is a shared prerequisite for *every* client** — do it regardless of
> which one you use. The rest of Part 1 (the `.mcp.json` file, the `/mcp` reconnect) is Claude
> Code-specific; the other clients have the equivalent in Part 1B.

> **📌 Platform note — read this first.** This guide works on **both macOS and Windows** (and
> Linux, which follows the macOS commands). Wherever a step differs, you'll see a **macOS / Linux**
> block and a **Windows** block — run only the one for your machine.
>
> - **Paths are placeholders — substitute your own.** `/path/to/hcl_mcp` means *wherever you
>   cloned this repo* (e.g. `/Users/you/dev/hcl_mcp` on macOS, `/home/you/hcl_mcp` on Linux,
>   `C:\Users\you\hcl_mcp` on Windows). `/usr/local/…` and `C:\Radiance` are the *conventional*
>   engine-install locations — use whatever you actually chose in [Appendix A](#a--installing-the-engines-optional--for-live-simulation). Nothing here is tied to a
>   specific machine.
> - Windows uses backslashes (`\`) in paths and a semicolon (`;`) — not a colon (`:`) — to
>   separate entries in list variables like `RAYPATH`. Engine executables get a `.exe` suffix.
> - On Windows, "terminal" means **Windows Terminal** or **PowerShell** (search the Start menu),
>   or the terminal panel inside VS Code.
> - **Honesty:** this project is developed and validated on macOS. The Windows commands below are
>   the standard equivalents (all three engines and `uv` ship for Windows), but the full pipeline
>   hasn't been end-to-end validated on a Windows box here — treat Windows as "should work," not
>   "certified," and see [§A](#a--installing-the-engines-optional--for-live-simulation) if an engine misbehaves.

### Step 1.1 — Open a terminal and install the project's dependencies

A "terminal" is the text window where you type commands. Open it, then copy-paste the two lines
for your platform, pressing Enter after each. (`cd …` means "go into this folder"; `uv sync …`
downloads the Python libraries the toolbox needs — `uv` is a Python package manager; if you don't
have it, install it from [astral.sh/uv](https://github.com/astral-sh/uv) (one line — see
[Appendix A](#a--installing-the-engines-optional--for-live-simulation)).)

**macOS / Linux** — open the **Terminal** app (or the VS Code terminal panel):

```bash
cd /path/to/hcl_mcp/hcl-mcp
uv sync --extra dev
```

**Windows** — open **Windows Terminal** or **PowerShell**, and use *your* project path:

```powershell
cd C:\Users\<you>\path\to\hcl-mcp
uv sync --extra dev
```

Wait for it to finish (you'll get your prompt back). You only ever do this again if the
project's code changes.

### Step 1.2 — What connects the toolbox to Claude (you don't edit this — just know it exists)

There's a small settings file at the project root:
`/path/to/hcl_mcp/.mcp.json` (on Windows,
`C:\Users\<you>\path\to\hcl_mcp\.mcp.json`). It tells Claude Code: *"here's a toolbox called
`hcl-mcp`, start it like this, and here's where to find the simulation engines."* Claude reads
this file **only when it starts up** — which is why the next step is to restart.

> On Windows the engine paths *inside* this file must point at your Windows install locations
> (e.g. `C:\Radiance\bin`) using `;` separators in list variables — see [§A](#a--installing-the-engines-optional--for-live-simulation) for the exact values.

### Step 1.3 — Restart Claude Code so it loads the toolbox

This is the step beginners miss. **Claude only notices the toolbox when it starts up.**

1. Make sure Claude Code is open in the **outer** project folder — the repo root
   **`/path/to/hcl_mcp`** (Windows: **`C:\Users\<you>\hcl_mcp`**), i.e. wherever you cloned it.
   That's where the `.mcp.json` settings file lives. If you opened a different folder, close and
   reopen Claude Code pointing at this one.
2. **Quit Claude Code completely and reopen it.** (Alternatively, type `/mcp` in the chat and
   choose to reconnect.)
3. The first time, Claude will **ask permission** to start the `hcl-mcp` server. **Click
   Approve / Yes.** If you don't approve it, no tools appear.

> **Naming note so you're not confused later:** the server is named **`hcl-mcp`**, so its tools
> appear in Claude with the prefix `mcp__hcl-mcp__` (e.g. `mcp__hcl-mcp__validate`) and the
> slash-command prompts as `/mcp__hcl-mcp__…`. Long, but that's just how MCP names things.

### Step 1.4 — (Background info) The simulation engines are optional

The pure-Python spectral math (spectrum → circadian numbers) works with **nothing else installed**.
The heavier *simulation* tools call external physics engines — and these are **optional**:

- **Radiance** — the main light-simulation engine. Powers daylight grids, images, glare, annual runs.
- **Daysim** — year-long daylight and alertness simulations.
- **SMARTS** — a detailed physical sky spectrum (optional; a pure-Python `spectrl2` default exists).
- **`reinsrc.cal`** — a small helper file Radiance needs for the annual ("whole year") solar-disc step.

**If an engine is installed, those tools run for real; if it isn't, they return the exact command
*plan* instead — a valid result, not an error** (see [Three important facts](#three-important-facts-that-prevent-90-of-confusion)).
So you can run the whole guide today and install engines later, only for the workflows you need.

**To install them** — on **macOS, Linux, or Windows**, with download links (GitHub / NREL) and the
build/copy commands for each — see **[Appendix A — Installing the engines](#a--installing-the-engines-optional--for-live-simulation)**.
After installing one, point its `env` variable at it (Appendix A) and restart your client.

> If any engine path changes, **restart your AI client** again (same as Step 1.3) so it re-reads the settings file.

---

# PART 1B — Connect to Gemini CLI or Antigravity

*Skip this whole part if you only use Claude Code.* The hcl-mcp server is a **standard** MCP
server, so it plugs into **Gemini CLI** and **Google Antigravity** exactly as it does into Claude
Code — the **only** thing that changes is *which file you paste the config into*. Everything else
in this guide (Parts 2–7 — every tool, prompt, resource, and recipe) applies unchanged; you talk to
the tools in plain English the same way.

> **Shared prerequisites — do these once, for any client:**
>
> - **Step 1.1** (`uv sync --extra dev` in the `hcl-mcp` folder) — installs the Python deps.
> - **[Appendix A](#a--installing-the-engines-optional--for-live-simulation)** — the (optional) simulation engines, if you want live daylight/annual/glare results rather than command plans.
>
> Neither depends on which AI client you use.

### The one config block (identical in every client)

Every client uses the **same** `mcpServers` object. Replace `/path/to/hcl_mcp` with your repo
checkout and the `/usr/local/…` / `/path/to/smarts` engine paths with wherever you installed them
(Appendix A). Drop the `SMARTSPATH`/engine lines you don't use. On Windows use backslash paths, `;`
in `RAYPATH`, and `.exe` engine names:

```json
{
  "mcpServers": {
    "hcl-mcp": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/hcl_mcp/hcl-mcp", "hcl-mcp"],
      "env": {
        "PYTHONPATH": "/path/to/hcl_mcp/hcl-mcp/src",
        "HCL_WORK_ROOT": "/path/to/hcl_mcp/hcl_validation/results/work",
        "HCL_RADIANCE_BIN": "/usr/local/radiance/bin",
        "RAYPATH": ".:/usr/local/radiance/lib",
        "SMARTSPATH": "/path/to/smarts/smarts295bat",
        "HCL_DAYSIM_BIN": "/usr/local/daysim/bin"
      }
    }
  }
}
```

It's the same `mcpServers` object Claude Code keeps in `.mcp.json` — only the *file you paste it
into* differs. If a config file already has other keys, add `mcpServers` **alongside** them
(don't nest it); if it already has an `mcpServers` object, add the `hcl-mcp` entry inside it.

> **Where to put it.** The repo ships no pre-filled copies — every path in the block above is
> specific to one machine, so you create the file yourself:
>
> - Gemini CLI (project scope): `<your-checkout>/.gemini/settings.json`
> - Antigravity (workspace scope): `<your-checkout>/.agents/mcp_config.json`
>
> Paste the block above into either one for a project-scoped setup, or into the **global** locations
> below (`~/.gemini/settings.json` / `~/.gemini/config/mcp_config.json`) to get it in every project.
> **Replace every path with your own** (repo checkout + engine install locations) before relying on it.

### Gemini CLI

1. **Open (or create) the settings file** — pick one scope:
   - All projects: `~/.gemini/settings.json`
   - This project only: `/path/to/hcl_mcp/.gemini/settings.json`
2. **Paste the `mcpServers` block** above into it (merge alongside existing keys).
3. **Restart Gemini CLI.** On startup it auto-starts the defined servers and asks to trust them —
   approve `hcl-mcp`.
4. **Verify:** type `/mcp list` in the chat — you want `hcl-mcp … Connected` with its tool count.
   After editing the config later, `/mcp reload` re-reads it without a full restart.

> Newer Gemini CLI builds also have a `gemini mcp add` / `gemini mcp list` subcommand (run
> `gemini mcp --help` to check). The `settings.json` route above always works regardless of version.

### Google Antigravity (IDE and CLI)

Antigravity 2.0, the IDE, and its CLI **share one** MCP config file.

1. **Open the config** — either way works:
   - **As a file:** `~/.gemini/config/mcp_config.json` (global), or per-workspace
     `<your-project>/.agents/mcp_config.json`.
   - **From the IDE:** in the Agent side-panel, click the `…` menu at the top → **MCP Servers** →
     **Manage MCP Servers** → **View raw config**.
2. **Paste the `mcpServers` block** above into that file (merge alongside any existing servers).
3. **Save, then refresh/reconnect** — the *Manage MCP Servers* panel has a refresh control, or just
   restart Antigravity. Approve the server if prompted.
4. The hcl-mcp tools now appear in Antigravity's tool list — drive them exactly as in Parts 5–7.

### What's the same, what's different across the three clients

- **Same:** the 50 tools / 13 prompts / 14 resources; calling a tool in plain English ("Call
  `alpha_opic` …"); the run-or-emit behavior; and all of the *content* of Parts 2–7.
- **Different — only two things:**
  1. **The config-file location** (above).
  2. **Minor UI wording.** The health check in [Part 2](#part-2--check-that-it-actually-worked-30-seconds)
     uses `/mcp` in Claude Code and `/mcp list` in Gemini CLI; Antigravity shows status in its
     *Manage MCP Servers* panel. The slash-command **prompts** (§5.3) are surfaced per-client —
     type `/` and look for the `hcl-mcp` entries (in Claude Code they read `/mcp__hcl-mcp__…`).
- **Restart rule (all three):** every client reads its MCP config **only at startup**, so
  **restart or reload after any change** — the same lesson as [Step 1.3](#step-13--restart-claude-code-so-it-loads-the-toolbox).

---

# PART 2 — Check that it actually worked (30 seconds)

Do these three quick checks in the main chat. They confirm the toolbox is connected before you
rely on it.

### Check 2.1 — Is the toolbox connected?

List the connected MCP servers — the command depends on your client:

| Client                | How to list servers                                                                        |
| --------------------- | ------------------------------------------------------------------------------------------ |
| **Claude Code** | type`/mcp` in the chat                                                                   |
| **Gemini CLI**  | type`/mcp list` in the chat (`/mcp reload` to re-read after a config edit)             |
| **Antigravity** | open the Agent panel's`…` menu → **MCP Servers** → **Manage MCP Servers** |

You should see **`hcl-mcp`** listed as **connected**, with counts **50 tools, 13 prompts,
14 resources**. If you see "connected," you're good.

**If `hcl-mcp` is missing or says "failed":** the config file didn't load. Go back to your client's
setup ([Part 1](#part-1--one-time-setup-claude-code) for Claude Code, [Part 1B](#part-1b--connect-to-gemini-cli-or-antigravity) for the others) — confirm the config is in
the right place, **fully restart (or reload) the client**, and approve the server when asked. Make
sure Step 1.1 (`uv sync`) finished without errors.

### Check 2.2 — Is the toolbox healthy?

Type this in plain English in the chat:

> Call the hcl-mcp `validate` tool.

The assistant will run a self-test. **The one thing that matters is `"ok": true`** — that means the
lighting math is internally consistent. Most `checks[]` say `"passed": true`, but **one is
`"passed": false` on purpose**: `channel_vs_spd_alpha_opic` reports a large (~99.7%) EDI divergence
because the 9-channel reconstruction constant (§9.3a) deliberately isn't lux-calibrated — it's
*informative only* and does **not** gate `ok`. (A companion check, `channel_vs_spd_divergence_bounded`,
*does* gate it, and passes.) So **don't be alarmed by that single `passed: false` — a healthy server
shows `ok: true` with it present.**

### Check 2.3 — Are the simulation engines available?

Ask:

> Call `radiance_status` and `daysim_status`.

- **`available: true`** for an engine → the full set that uses it (daylight, electric, spectral,
  annual, glare) **runs for real**.
- **`available: false`** → you haven't installed that engine. That's **fine** — those simulation
  tools will print the exact command *plan* instead of running, which counts as a pass. Install the
  engine later if/when you need live results: see
  [Appendix A](#a--installing-the-engines-optional--for-live-simulation) (macOS / Linux / Windows, with download links).

So whatever you see here is valid — `true` means live, `false` means emit-only. Neither is a failure.

If all three checks look right, setup is done. 🎉

---

# 🚀 QUICK START — run your first HCL simulation (three simple walkthroughs)

Setup done? You can run a real study **right now**, just by typing plain English to your assistant.
No JSON, no coding — **describe what you want and name an example file, and the assistant fills in
the rest.** (If you make a typo, the assistant just asks you to clarify — nothing breaks.)

Below are **three complete walkthroughs**, quickest first. Each shows the exact words to type
(**You type**) and what comes back (**You'll see**). All of them use the ready-made example files in
[`inputs/`](inputs/), so they work today. Do them in order the first time.

> **A 60-second word list** (all re-explained later — don't memorize):
>
> - **spectrum / SPD** — a light's "colour recipe," its energy at each wavelength.
> - **mel-EDI** — how strongly the light hits your body clock (*melanopic Equivalent Daylight
>   Illuminance*), in lux. Higher = more alerting / circadian punch.
> - **mel-DER** — mel-EDI per ordinary lux; a "how circadian is this light, unit for unit" ratio.
> - **standard / compliance** — grading a result against a published target (e.g. *Brown 2022*
>   wants **≥ 250 mel-EDI** during the day).

## Walkthrough 1 — a light's circadian verdict (60 seconds, no room, nothing to install)

*The fastest possible run: hand it one light's spectrum, get its body-clock verdict.* Pure math —
works even with no simulation engines installed.

```
You type:   Analyze inputs/spd/L09_neutral.spd for me — give me its CCT and mel-DER,
            then check it against the brown_2022 daytime circadian target.
```

**You'll see:** a colour temperature (~**3985 K**, a neutral white), a mel-DER (~**0.61**), and a
pass/fail note against the 250 mel-EDI daytime target.

**See the contrast:** run the same line for `L09_warm.spd` (2700 K) and `L09_cool.spd` (6500 K) — the
same fixture at three colour temperatures — and ask for one table. mel-DER more than **doubles**
warm → cool: the evidence for "cool light to wake up, warm light to wind down."

> Prefer a guided version? Type `/mcp__hcl-mcp__spd_to_circadian` and answer its questions instead.

## Walkthrough 2 — daylight in a real room (the representative simulation)

*The main event: pour daylight into a 3D room and measure what actually reaches the occupant's eyes.*
Uses the Radiance engine if installed — and if it isn't, you simply get the command *plan* back
instead, which is still a valid result.

```
You type:   Run a daylight study on the example office: import inputs/geometry/office_room.obj,
            build an Athens sky for June 21 at noon, run the daylight grid at the desk/eye
            sensors, and tell me the mel-EDI at each point and whether it passes brown_2022.
```

**You'll see:** the assistant imports the room (a furnished office with one **south-facing** window — the
model is authored in the true-north frame with the window in the −Y "South" wall, so `north_angle_deg 0`),
builds the sky, traces the daylight, and reports **mel-EDI per sensor** — highest near the window, falling
off with depth — plus a pass/fail. (Numbers move with the sky and orientation; the illustrative figures
elsewhere in this guide were captured on an older north-facing version of the room, so a south-facing Athens
noon will read **higher** near the glass — re-run to get current numbers.)

**Try a "what-if":** run the same request with `inputs/geometry/office_room_blinds.obj` (the *same*
room, now with venetian blinds) and ask for a side-by-side table. You'll watch the blinds cut both
daylight **and** glare — the classic comfort trade-off, quantified.

> Guided version: `/mcp__hcl-mcp__hcl_grid_study`. Want the eye-level glare image too? Add
> `/mcp__hcl-mcp__fisheye_eye_analysis` on the same scene.

## Walkthrough 3 — a full study, start to finish (one guided prompt)

*The whole thing in one command: set a goal → design the fixtures → simulate → estimate energy →
get a written report.* The `hcl_studio` prompt runs the study and asks you for each input
conversationally — you just answer.

```
You type:   /mcp__hcl-mcp__hcl_studio

Then answer its questions with:
  • what you're designing:  "a 4.3×7.3 m Athens office, one south window, desks by the glass"
  • daylight-aware?         yes
  • the room:               inputs/geometry/office_room.obj   (units m, up-axis Z, north_angle_deg 0 → window in the South wall → south-facing)
  • the fixture:            inputs/luminaires/L09_cool.ies    (a 6500 K luminaire)
  • the weather:            inputs/weather/GRC_Athens.167160_IWEC.epw
  • your targets:           250 mel-EDI at the eye, 500 lux on the desk
```

**You'll see:** the assistant moves through eight phases — check engines → pin the goal → import the
room → measure the daylight baseline → size the fixtures → place a real luminaire → simulate the
combined result → estimate energy — and finally writes a `report.md` / `report.html` with a
**target-vs-achieved** verdict. It **saves progress after every phase**, so if the chat is
interrupted you can say **"resume study &lt;name&gt;"** and pick up where you left off.

> This is the "front door" — it ties Walkthroughs 1 and 2 (plus fixtures and energy) into one
> deliverable. Everything it does by hand is spelled out in
> [Part 5](#part-5--drive-it-yourself-in-full-detail).

### Where to go next

- Use **your own** building / light / weather → just drop your file into the matching `inputs/`
  subfolder: [Part 4](#part-4--use-your-own-data-just-drop-files).
- More worked "what-if" comparisons with real numbers →
  [Part 4.5 — Scenarios](#part-45--built-in-scenarios-use-what-is-in-the-folder).
- Understand every prompt, tool, and knob → [Part 5](#part-5--drive-it-yourself-in-full-detail),
  with plain-English "what to type" cards in
  [§5.7](#57--copy-paste-chat-scripts-exactly-what-to-type).

---

# PART 3 — Let the assistant test everything for you (the easy path)

Before driving the tools by hand, you can have a specialized helper agent exercise the **entire**
toolbox automatically and write you a report. You don't make any tool calls yourself.

> **Client note:** the one-shot **`hcl-mcp-tester`** agent below is a **Claude Code** feature
> (it relies on Claude Code's sub-agents). In **Gemini CLI** or **Antigravity**, there's no
> packaged tester agent — instead just ask your assistant in plain English to "run `validate`,
> then exercise each workflow in `hcl_validation/TEST-PLAN.md` and summarize pass/fail," or simply
> work through Parts 5–7 yourself. The tools, prompts, and resources being tested are identical.

In the main chat (Claude Code), paste this:

> Use the **hcl-mcp-tester** agent to run the full validation against
> `hcl_validation/TEST-PLAN.md`, using the inputs selected in
> `hcl_validation/inputs/active_inputs.json`. Write the report to
> `hcl_validation/results/VALIDATION-REPORT.md`.

It runs the health checks, every workflow end-to-end, renders all 13 prompts, reads all 14
resources, and writes a PASS/FAIL report. A tool that returns "didn't run, here's the plan" is
scored a **pass**, and the year-long sims are capped to a tiny window so the run takes minutes.

**The outputs are organized so you can review each workflow on its own.** Instead of one flat pile of
files, the agent writes **one folder per workflow** under `hcl_validation/results/` —
`W0-orientation/`, `W1-spectral/`, `W2-geometry/`, `W3-grid/`, `W5-electric/`, `W6-annual/`, … each
containing:

- **`RESULTS.md`** — the actual numbers for that workflow (mel-EDI per point, CCT, UGR, kWh, …) with a
  pass/fail verdict per test;
- the workflow's **headline data files** at the top (`grid.csv`, glare `.hdr` maps, the room `manifest.json`,
  the studio `report.html`, `preview_*.png`, …);
- a **`work/`** subfolder with the intermediate engine files (Radiance `.rad`/`.oct`/`.hdr`, scripts, `.pts`,
  `.wea`) — the "how it was computed" material.

When it's done, open the index at [`hcl_validation/results/VALIDATION-REPORT.md`](results/VALIDATION-REPORT.md)
and click through to any workflow's `RESULTS.md`.

> **📋 Want to see exactly what a correct return looks like — real numbers, not descriptions?**
> [`TEST-PLAN.md`](TEST-PLAN.md) is now a worked cookbook: every tool, prompt, and workflow carries the
> **actual captured output** from a fully-engined run (Radiance 6.1a + Daysim + SMARTS) plus a
> value-correctness assertion. Read it alongside this guide when you want to know whether *your* numbers
> are in the right ballpark (e.g. eye mel-EDI tens–hundreds of lux at a window, sky CCT ~8500 K, mel-DER
> 0.41→0.98 across the L09 CCTs, DGP ~0.17). It also records the defects a strict run surfaces.

---

# PART 4 — Use your OWN data (just drop files)

Everything so far used the example files in [`inputs/`](inputs/). To test *your* building, climate,
fixture, or spectrum, **just drop a file with the right extension into the matching subfolder** —
you don't edit any JSON:

| Drop into…            | Name it…                                 | Becomes                                                     |
| ---------------------- | ----------------------------------------- | ----------------------------------------------------------- |
| `inputs/geometry/`   | `<anything>.obj` (+ `<anything>.mtl`) | your room model                                             |
| `inputs/weather/`    | `<anything>.epw`                        | your climate (the`.wea` is derived for you if missing)    |
| `inputs/luminaires/` | `<anything>.ies`                        | your fixture                                                |
| `inputs/spd/`        | `<anything>.spd`                        | a daylight or lamp spectrum                                 |
| `inputs/sensors/`    | `<anything>.pts`                        | sensor points (optional — else auto-derived from the room) |

**How it gets picked up.** Each entry in [`inputs/active_inputs.json`](inputs/active_inputs.json) is
set to `"auto"`. The tester (Part 3) — and you, by the same rule — globs each subfolder by extension
and uses the file it finds. If a shipped sample *and* your file are both present, **yours wins** (the
samples are listed in the file's `_resolution._sample_files`); genuine ambiguity is flagged, not
guessed. So in most cases the only step is "drop the file."

> ✅ **The OBJ now works without writing `material_map.json`.** The importer still hard-fails on an
> unmapped group (that negative case is tested on purpose in W2.2), **but the tester shields you**:
> if no on-disk map covers your OBJ's groups, it runs a dry-run, then **auto-generates** a complete
> map from your group names + the `.mtl`'s colors (reflectances are *illustrative*, and the report
> says so). To pin materials exactly, drop a `geometry/<name>_material_map.json` whose keys match
> your groups — an on-disk map that covers the groups always wins over auto-generation. The full
> material-map format is in [Part 5.0](#authoring-each-input-when-you-bring-your-own).

> Prefer explicit control over discovery? You can still set any field in `active_inputs.json` to a
> specific path — an explicit, existing path always wins over `"auto"`.

---

# PART 4.5 — Built-in scenarios (use what is in the folder)

The shipped `inputs/` folder deliberately contains **more than one of some things**, so you can run
**comparisons**, not just one-offs:

- **Four room models — two ± blinds pairs** (all the *same* furnished office, authored in the true-north
  frame → `north_angle_deg 0`):
  - `geometry/office_room.obj` — one **south-facing** window (in the −Y "South" wall); and
    `geometry/office_room_blinds.obj` — the same room with **venetian blinds** added.
  - `geometry/office_room_corner_window.obj` — a wraparound **corner window**, a **south-west corner**
    (glazing on the −Y South and −X West walls, with compass-named per-facade groups); and
    `geometry/office_room_corner_window_blinds.obj` — the same with a blind on each leg.

  Within each pair only the blinds differ (isolates the blinds' effect); across the pairs only the
  window geometry differs (single south window vs. SW corner). Each OBJ ships its own pinned
  `<name>_material_map.json` (all `north_angle_deg 0`), so just point the tools at the OBJ. **Second path:**
  each model also ships as a hand-authored Radiance scene in `geometry/radiance/` (`<model>.rad` +
  `materials.rad` + `luminaires_L09.rad`) you can feed straight to `run_grid`/`run_annual`.
- **One tunable-white fixture at three CCTs** — `luminaires/L09_warm.ies` (2700 K),
  `L09_neutral.ies` (4000 K), `L09_cool.ies` (6500 K) — a real Glamox C95-R600×600 LED — each with
  its **matching measured spectrum** `spd/L09_warm.spd` / `L09_neutral.spd` / `L09_cool.spd`
  (PhotoLED proxy SPDs). Same photometry, different colour → isolates CCT's effect on the body clock.

Because multiple files of one class are present, plain "auto" discovery would be **ambiguous** (it
picks the alphabetically-first and warns). So for these scenarios you **name the file you want** —
either in the prompt, or by setting the field in [`inputs/active_inputs.json`](inputs/active_inputs.json).
The base defaults there are `office_room.obj` + `L09_neutral.ies` + `L09_neutral.spd`; each scenario
below swaps one axis.

### Scenario S1 — Blinds A/B (daylight & glare)

*What does adding venetian blinds do to daylight level and glare at the desk?* Run the **same**
daylight study on both models and compare.

```
You type:   Run /mcp__hcl-mcp__hcl_grid_study for "furnished office, one window, June 21 noon,
            Athens" using inputs/geometry/office_room.obj. Then run /mcp__hcl-mcp__fisheye_eye_analysis
            on the same scene for glare. Note the eye mel-EDI and the UGR.

You type:   Now do exactly the same two runs with inputs/geometry/office_room_blinds.obj instead,
            and give me a side-by-side table: photopic lux, mel-EDI, UGR — bare window vs blinds.
```

- **What good looks like:** the blinds model shows **lower** illuminance and mel-EDI at the eye and
  **less glare** — the classic daylight-vs-comfort trade-off, quantified.
- **Measured here** *(June 21 noon, Athens, Radiance 6.1a — captured when this window faced **north**;
  your numbers will differ with sky/cloud, and will read **higher** now the window faces south — re-run):*

  | at the eye                    | bare window |      with blinds |
  | ----------------------------- | ----------: | ---------------: |
  | photopic (near window)        |     137 lux | **21 lux** |
  | mel-EDI (near window)         |         155 |     **25** |
  | mel-EDI (far point)           |         261 |     **78** |
  | DGP                           |       0.172 |  **0.162** |
  | window glare-source luminance |         215 |     **45** |

  Blinds cut eye mel-EDI ~70–85% (most near the window, ~84% there vs ~70% deep in the room) and drop
  DGP + the window's glare-source luminance (~4×). Note that **UGR read 0 in both** models here (no
  discrete source bright enough to score) — so on a daylit window, **DGP and the glare-source luminance
  are the meaningful discriminators, not UGR.**
- **Same idea, annual:** swap `hcl_grid_study` for `annual_circadian_dose` (tiny `period`!) to see
  the blinds' effect on the *yearly* circadian dose and hours-above-threshold.

### Scenario S1b — Window geometry A/B (single south window vs. SW corner)

*How much does a wraparound corner window change daylight vs. a single window of the same room?* Run the
**same** study on `office_room.obj` (single south window) and `office_room_corner_window.obj` (south-west
corner) and compare — the corner has glazing on two walls (South + West), so expect higher and more even
daylight (and a different glare geometry, with a west-afternoon component). All models are `north_angle_deg
0`, so you just swap the OBJ. Add the `_blinds` variants for the full 2×2 (geometry × blinds) matrix. The
corner's two facades carry distinct glazing modifiers (`Rad_Glazing_South_T073` / `_West_T073`), so each
can be evaluated independently (south vs. west).

### Scenario S2 — Tunable-white CCT sweep (spectrum only, no room needed)

*How "circadian" is each CCT per lux?* Pure spectral math — instant, needs no geometry or engine.

```
You type:   For each of inputs/spd/L09_warm.spd, L09_neutral.spd, L09_cool.spd, call
            spectral_metrics and alpha_opic (alpha=5). Give me one table: CCT, mel-DER,
            mel/photopic ratio — warm vs neutral vs cool.
```

- **What good looks like:** mel-DER rises monotonically warm → cool — the evidence for "warm light in
  the evening, cool light in the morning."
- **Measured here** *(the three shipped L09 spectra — these are deterministic, you'll get the same):*

  | SPD         |    CCT | mel-DER | mel/photopic |
  | ----------- | -----: | ------: | -----------: |
  | L09_warm    | 2694 K |   0.407 |        0.369 |
  | L09_neutral | 3985 K |   0.610 |        0.553 |
  | L09_cool    | 6471 K |   0.982 |        0.889 |

  mel-DER more than **doubles** warm→cool at the same lux. (These SPDs are *relative* PhotoLED proxies,
  so `alpha_opic`/`spectral_metrics` attach a `scale_warning` and the absolute EDIs are shape-only;
  CCT and mel-DER are scale-invariant and unaffected.)
- **Go further:** feed each through `compliance` (standard `brown_2022`) at a fixed 500 lx desk level
  to see which CCT *passes* a daytime circadian target and which doesn't.

### Scenario S3 — Tunable-white in the real room (electric + energy)

*Hold the task illuminance fixed and watch the circadian dose move with CCT.* Combines the fixture's
real photometry (IES) with its real spectrum (SPD) in the actual room.

```
You type:   Run /mcp__hcl-mcp__electric_lighting_design for the office using
            inputs/geometry/office_room.obj, fixture inputs/luminaires/L09_neutral.ies paired with
            inputs/spd/L09_neutral.spd, a 2×2 ceiling grid, target 500 lux + 250 mel-EDI.

You type:   Re-run it twice more — L09_warm.ies + L09_warm.spd, then L09_cool.ies + L09_cool.spd —
            same layout. Table the result: achieved lux (should stay ~500), UGR, kWh/m², and
            mel-EDI at the eye for warm / neutral / cool.
```

- **What good looks like:** lux and energy stay roughly constant across the three; **mel-EDI climbs
  with CCT** — so "tune to cool for an alertness boost without changing the light level."
- **Measured here** *(the fixture's photometry barely moves while its spectrum does):* `ies_analyze`
  gives warm **4467 lm / 117.6 lm·W⁻¹**, neutral & cool **4702 lm / 123.7** — same beam, same LOR≈1.0 —
  while the S2 table shows mel-DER climbing 0.407 → 0.610 → 0.982. So holding the *task* lux fixed, the
  circadian dose rises purely from CCT.
- **One caveat for the *combined* run:** the room-level "hold 500 lux, vary CCT" demo needs the
  **electric** light actually placed in the room (`run_grid(electric_lights=…)`). That payload comes
  from a `type:"luminaire"` OBJ group (see 5.3.7) or a hand-built `electric_lights` list — the shipped
  `office_room.obj` has no luminaire group, so by default you'll see the *daylight* grid + the
  spectrum/photometry comparison above, not the combined electric grid.
- **Full study:** `/mcp__hcl-mcp__hcl_studio` (5.3.10) wraps S1+S3 into one report — give it the
  blinds model + `L09_cool.ies` and a mel-EDI target for a complete start-to-finish demo.

> **Bring your own?** The moment you drop *a single* `your.obj` / `your.ies` / `your.spd` into the
> right subfolder, discovery is unambiguous again and these scenarios run against **your** data with
> the same prompts — see [Part 4](#part-4--use-your-own-data-just-drop-files).

---

# PART 5 — Drive it yourself, in full detail

This is the heart of the guide. It covers, in order:

- **5.0** — the input files you need, and which workflow needs which.
- **5.1** — the three building blocks (tools vs prompts vs resources) and how to invoke each.
- **5.2** — five concepts you must understand to use the toolbox well.
- **5.3** — the **13 prompts**, each in detail.
- **5.4** — the **46 tools**, grouped, with their key inputs/outputs.
- **5.5** — the **14 resources**.
- **5.6** — recipes for chaining tools yourself, and how to get the most out of it.
- **5.7** — copy-paste chat scripts: the exact words to type for every prompt and a manual run.

---

## 5.0 — The input files you need (start here)

There are **7 classes of input**. Only the *simulation* paths need files on disk; the spectral
math needs nothing but numbers you paste. Everything below already ships under `inputs/` so you
can run the whole tour before supplying your own.

| # | Class                         | What it is                                      | Format                                                   | Needed for                           | Already provided                                                                                                                                                                                                                          |
| - | ----------------------------- | ----------------------------------------------- | -------------------------------------------------------- | ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | **Room geometry**       | a 3D model of the space                         | Wavefront`.obj` (one group per surface class), or pre-authored Radiance `.rad` | any Radiance run                     | `inputs/geometry/office_room{,_blinds,_corner_window,_corner_window_blinds}.obj` (+ `.mtl`); or the hand-authored `inputs/geometry/radiance/*.rad`                                                                              |
| 2 | **Weather**             | a year of hourly climate                        | EnergyPlus`.epw`; `.wea` derived from it             | spectral-sky + annual                | `inputs/weather/GRC_Athens.167160_IWEC.epw` (`.wea` auto-derived)                                                                                                                                                                     |
| 3 | **SPD**                 | a spectrum: "how much light at each wavelength" | 2-column text`wavelength_nm value`, 380–780 nm        | spectral metrics; lamp/surface color | `inputs/spd/L09_warm.spd`, `L09_neutral.spd`, `L09_cool.spd` (2700/4000/6500 K)                                                                                                                                                     |
| 4 | **Luminaire (IES)**     | a light fixture's photometry                    | IESNA LM-63`.ies`                                      | electric / glare / energy            | `inputs/luminaires/L09_warm.ies`, `L09_neutral.ies`, `L09_cool.ies` (one tunable fixture, 3 CCTs)                                                                                                                                   |
| 5 | **Materials**           | reflectance / glazing per surface               | a JSON map you author (**not** read from CAD), or `radiance/materials.rad`      | any Radiance run                     | one `<name>_material_map.json` per OBJ (all `north_angle_deg 0`; corner maps carry per-facade `Rad_Glazing_South/West_T073`), pinned exact; **auto-generated** for your own OBJ                                                 |
| 6 | **Sensor + eye points** | where to measure                                | `[x y z dx dy dz]` rows in a `.pts`, or auto-derived | grid / annual / image                | `inputs/sensors/office_room_grid.pts` (EN work-plane, `workplane_grid`), `observer_1.pts`/`observer_2.pts` (eye, `observer_points`), `sensor_1.pts`/`sensor_2.pts` (daylight-dimming, `photosensors`); or use `derive_sensors=true` |
| 7 | **Compliance target**   | which standard to judge against                 | a*selection*, not a file                               | the pass/fail step                   | chosen at call time                                                                                                                                                                                                                       |

### Which workflow needs which files

| Workflow (prompt)               | Geometry | Weather |  SPD  |  IES  | Materials | Points | Target |
| ------------------------------- | :------: | :-----: | :---: | :---: | :-------: | :----: | :----: |
| 5.1`explain_concept`          |    —    |   —   |  —  |  —  |    —    |   —   |   —   |
| 5.2`spd_to_circadian`         |    —    |   —   |  ✅  |  —  |    —    |   —   |   ✅   |
| 5.3`spectral_sky_from_epw`    |    —    |   ✅   |  —  |  —  |    —    |   —   | (opt) |
| 5.4`import_obj_room`          |    ✅    |  (opt)  |  —  |  —  |    ✅    |  auto  | (opt) |
| 5.5`hcl_grid_study`           |    ✅    |  (sky)  | (opt) |  —  |    ✅    |   ✅   |   ✅   |
| 5.6`fisheye_eye_analysis`     |    ✅    |  (sky)  |  —  |  —  |    ✅    |  view  |   ✅   |
| 5.7`electric_lighting_design` |    ✅    |  (sky)  | (opt) |  ✅  |    ✅    |   ✅   |   ✅   |
| 5.8`annual_circadian_dose`    |    ✅    |   ✅   |  —  |  —  |    ✅    |   ✅   |   ✅   |
| 5.9`annual_alertness`         |  (opt)  |   ✅   |  —  |  —  |   (opt)   |  1 pt  |   —   |
| 5.10`hcl_studio`              |  (opt)  |  (opt)  | (opt) | (opt) |   (opt)   |  auto  |   ✅   |

### Authoring each input (when you bring your own)

- **Geometry (`.obj`)** — export from Rhino/Revit/SketchUp/Blender. Put **each surface class
  in its own group** (`g`/`usemtl`: floor, walls, ceiling, each window, shading), include
  vertex normals (`vn`). List its group names — macOS / Linux:
  `grep -E '^(g|usemtl) ' your.obj | sort -u`; Windows PowerShell:
  `Select-String -Path your.obj -Pattern '^(g|usemtl) ' | ForEach-Object { $_.Line } | Sort-Object -Unique`
  (or just run `import_geometry(dry_run=true)`, which lists them on any OS). The OBJ carries
  **no color/material** — that's class 5.
- **Weather (`.epw` → `.wea`)** — get an EPW from *climate.onebuilding.org* or
  *energyplus.net/weather*. Make the `.wea` with Radiance's `epw2wea` — macOS / Linux:
  `epw2wea your.epw your.wea` (on your PATH after installing Radiance, or run it from your
  `$HCL_RADIANCE_BIN`; on Windows it's `epw2wea.exe`). Don't have Radiance? The server's
  `generate_subhourly_wea` / `run_annual` tools emit the `epw2wea` command for you to run.
- **SPD** — two columns, `wavelength_nm value`, 380–780 nm. **Relative is fine** for color/
  melanopic-ratio metrics; you only need **absolute** (W·m⁻²·nm⁻¹) for absolute mel-EDI. No
  file at all if you use a built-in preset (D65, A, FL1–12, …).
- **Materials (`material_map.json`)** — a dict mapping **every** OBJ group to either a
  library-name string or an inline dict
  `{"type": "plastic|glass|ground|context|luminaire|floor", "refl"|"tvis"|"spd": …}`. Plus
  `units` (`mm|cm|m|ft`), `up_axis` (`Y|Z`), `north_angle_deg`. **An unmapped group hard-fails at
  the importer** — but for the validation kit you can **skip authoring this entirely**: the tester
  auto-generates a complete (illustrative) map from your group names + `.mtl` when you don't supply
  one (Part 4). Author it yourself only when you want exact, measured reflectances. To control
  materials precisely, name the file `geometry/<name>_material_map.json` so it's discovered alongside
  your OBJ.
- **Points** — best to let `import_geometry(derive_sensors=true)` generate scene-aligned work-
  plane and eye-level points; for methodology-grade grids, use `workplane_grid` (EN 12464-1
  work-plane illuminance grid → `grid.pts`, now with concave-room + footprint-clip support),
  `observer_points` (workstation eye sensors → `observer_*.pts` + `glare_views`, now with a
  footprint check), or `photosensors` (daylight-dimming reference sensors →
  `sensor_*.pts`); or hand-write `[x y z dx dy dz]` rows (for melanopic the
  sensor is **vertical at the eye**, facing the window). Use `preview_scene` to render a PNG
  sanity-check of wherever the points ended up.
- **Target** — pick `standard` ∈ `brown_2022 | well_v2_l03 | iso_cie_8995_1_2025 | en_17037`
  (plus `period` and `daylight_met`). No file.

**You normally don't point anything at your files** — just drop them in the right subfolder by
extension and they're auto-discovered (Part 4). `inputs/active_inputs.json` keeps the optional
overrides (`geometry_obj`, `material_map`, `epw`, `wea`, `ies`, `spd_daylight`, `spd_luminaire`,
`points`) plus the `site` and `compliance` settings — set a field to an explicit path only if you
want to override discovery.

---

## 5.1 — The three building blocks, and how to invoke each

| Block              | What it is                   | How you call it                                                                                                                                                  |
| ------------------ | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Tool**     | one action                   | Ask in plain English:*"Call `alpha_opic` with the D65 preset and alpha=5."* The assistant fills the parameters and runs it.                                  |
| **Prompt**   | a guided multi-tool workflow | Type the slash command (shown here in Claude Code's spelling:`/mcp__hcl-mcp__spd_to_circadian`). The assistant then runs the tools for you, asking for inputs. |
| **Resource** | a reference document         | Ask:*"Read the hcl-mcp resource `hcl://reference/coefficients`."*                                                                                            |

> **Prompt slash commands across clients.** Every `/mcp__hcl-mcp__<name>` shown in this guide is
> **Claude Code's** spelling. The prompts themselves are the same in every client — only how you
> trigger them differs: in **Gemini CLI** and **Antigravity** type `/` and pick the `hcl-mcp`
> prompt by name from the list (or just describe the workflow in plain English and the assistant
> runs the same tool chain). Tools and resources are called the same way everywhere.

**Why prompts exist:** a prompt is a script. When you trigger it, the server hands the assistant an
ordered plan ("first analyze the spectrum, then compute alpha-opic, then check compliance"),
and the assistant executes that plan with the right tools — asking you only for the inputs it needs.
You *can* call every tool by hand (Part 5.4), but prompts save you from remembering the order.

**Important limitation:** the auto-tester agent (Part 3, Claude Code) **cannot** trigger
slash-command prompts — that's why *you* drive them here, as a real user would.

---

## 5.2 — Six concepts that make everything click

**1. Channels and `channel_type`.** A full spectrum (hundreds of numbers) is heavy to simulate,
so the toolbox bins it into **channels**. `channel_type: 0` = **3 channels** (red/green/blue);
`channel_type: 1` = **9 channels** (three sub-bands each). **9-channel (type 1) is the default
and recommended** — it's far more accurate for melanopic/circadian work. Use 3-channel only for
glare (`glare_ugr` defaults to it) or quick visual-only checks. **Only `0` or `1` are valid — pass
one of those; no other value is supported.** The key chain is: `spd_to_channels` (spectrum →
channels) → `circadian_metrics` (channels → photopic/melanopic/neuropic lux).

**2. Relative vs absolute SPD.** A *relative* spectrum (peak ≤ 1.5) tells you **shape** —
enough for CCT, mel-DER, mel/photopic ratio. An *absolute* spectrum (W·m⁻²·nm⁻¹) is needed for
**absolute** melanopic-EDI / lux. If you feed a relative SPD to `alpha_opic`, it attaches a
`scale_warning` so you're never misled.

**3. Capability gating.** Every simulation tool takes a `run` flag (default `true`). If the
engine is missing — or you pass `run: false` — the tool returns `{"ran": false, "commands":[…]}`,
the exact plan it would have executed. That's a valid result, not an error. Great for previewing
a heavy run before committing to it.

**4. `scene_sets` shape.** Radiance tools (`run_grid`, `run_image`, `glare_ugr`) take
`scene_sets`: for **3-channel**, one list of `.rad` paths; for **9-channel**, **three** lists
(blue/green/red bin sets). `import_geometry` returns `geometry_set` + `material_sets` already in
this index-aligned shape — you compose them with a sky into `scene_sets`. The annual tools use a
slightly different `channel_scenes` shape: one dict (3ch) or three dicts (9ch), each
`{materials:[paths], geometry:<one .rad>, sky_color:[r,g,b]}`.

**5. `work_dir` and performance.** Tools that write files accept `work_dir` (defaults to the
server's work root). Outputs land there: `.rad`, `.hdr`, `.csv`, reports. **Tip — keep results tidy by
passing a `work_dir` per workflow** (e.g. `hcl_validation/results/W3-grid/work`) instead of letting every
tool dump into one shared folder; that's exactly how the validation kit produces its per-workflow
`results/<SEC>/` layout (Part 3). For anything annual, **always pass a tight `period`** like
`[[6,21,8],[6,21,18]]` (June 21, 8am–6pm) — a full year is 8760 hours and can take 10+ minutes.

**6. `advisories` — the tool telling you how to read its own answer.** Any dict-shaped result may carry an
`advisories` list of `{code, severity, message, field?}`. They attach at the **tool-registration seam**, so
**every** tool can produce them ([ADR-0005](../docs/adr/0005-advisories-attach-at-the-registration-seam.md)).
The key is **absent entirely** when nothing needs saying — an empty `[]` on every clean result would just
train you to stop looking, so if you see the key, read it.

| Severity | Means | What to do |
|---|---|---|
| `error` | the result is probably **not usable as-is** | fix the input before quoting anything |
| `warn` | usable, but **easy to misreport** | quote the number *with* the caveat |
| `info` | a **default was applied** | confirm it's the one your brief/standard wants |

They are **reporting, not physics** — each one re-reads a value the tool already computed, so an advisory
never changes a number. An advisory is **not** a failure. But quoting a figure and *silently dropping* its
advisory is a reporting defect: that's how a mel-EDI inferred from binned channels (up to ~8% high on a
narrow-band source) ends up in a compliance table with no asterisk.

Three fire on the example files and are **expected, not bugs**:

- `ALBEDO_NOT_MEASURED` — on every spectral-sky call against the shipped Athens EPW. IWEC/TMY2 files write
  a literal `0.000` ground reflectance instead of the "missing" sentinel; the toolkit treats sub-physical
  values as missing, substitutes a documented default, and says so. Substituting is right; reporting it as
  *measured* would not be.
- `GEOMETRY_HEALTH_UNCLEAN` — on `office_room.obj`: one `NOT_ENCLOSED` warning, because the glazing and
  luminaire groups are inset panels rather than sealed solids. An accepted property of the fixture.
- `MEL_DER_BINNED` — whenever you pass `channels` without `spd=`. Pass the source spectrum for the exact
  CIE S 026 value.

**One documented gap:** `circadian_metrics` with **multi-point** input returns a bare **list**, and lists
carry no advisories (wrapping one would change the tool's published contract). Check `mel_der_source` on
each point by hand there. Every other tool returns a dict.

---

## 5.3 — The 13 prompts, in detail

Run them in this order (simplest → full study). For each: what it's for, files needed, the tool
chain it runs, the parameters worth knowing, what a good result looks like, and how to push it
further.

### 5.3.1 `/mcp__hcl-mcp__explain_concept` — learn a concept (no inputs)

- **Argument:** `topic` (e.g. `mel-EDI`, `coefficients`, `overview`).
- **Files:** none.
- **What it does:** explains a metric/method in plain language, grounded in the reference
  resources. No simulation.
- **Good result:** a correct explanation citing the 9-channel coefficients / §9.3 caveats.
- **Go further:** follow up with `/explain_concept coefficients` then read
  `hcl://reference/coefficients` to see the actual numbers it's describing.

### 5.3.2 `/mcp__hcl-mcp__spd_to_circadian` — one light → a body-clock verdict

- **Argument:** `spd_description` (e.g. `4000 K LED downlight`).
- **Files:** an SPD — paste `inputs/spd/L09_neutral.spd` (4000 K), or say "use preset D65."
- **Tool chain:** `spd_to_channels` → `alpha_opic` → `spectral_metrics` → `compliance`.
- **Parameters worth knowing:** `channel_type: 1` (keep it); `standard` for the compliance step.
- **Good result:** CCT, mel-DER, mel-EDI, and a verdict vs your standard. **The verdict shape depends
  on the standard:** `brown_2022` / `iso_cie_8995_1_2025` → `{"result":"pass"|"fail","threshold":…}`;
  `well_v2_l03` → `{"result_points":0|1|3,"thresholds_mel_edi":{…}}` (points, not pass/fail — and the
  WELL "275" figure is the *EML* noon criterion, not the mel-EDI threshold); `en_17037` →
  `{"result":"n/a","flag":"non-circadian"}` (it's a daylight-illuminance standard, no melanopic limit);
  `ul_24480` → `{"result":"unsupported"}` (Circadian Stimulus, out of scope); `en_12464_1` is the
  **electric task** path (pass a `task` + `em/ugr/uo/ra`, not a `mel_edi`). Don't expect a bare pass/fail.
- **Go further:** run it three times on the shipped tunable-white spectra
  `L09_warm.spd` (2700 K) → `L09_neutral.spd` (4000 K) → `L09_cool.spd` (6500 K) and compare
  mel-DER — the single number that says "how circadian-active is this light per lux." That's
  **Scenario S2** (CCT sweep) in [Part 4.5](#part-45--built-in-scenarios-use-what-is-in-the-folder).

### 5.3.3 `/mcp__hcl-mcp__spectral_sky_from_epw` — a physical sky from weather

- **Argument:** `location_description` (e.g. `Athens, June 21 noon`).
- **Files:** the EPW `inputs/weather/GRC_Athens.167160_IWEC.epw` + a month/day/hour.
- **Tool chain:** `atmosphere_from_epw` → `spectral_sky_from_epw` → feeds the sky spectrum to
  `alpha_opic` + `spectral_metrics`; optionally `spectral_epw` / `spectral_sky_native`.
- **Parameters worth knowing:** `surface_tilt_deg` (90 = a vertical window) adds a ground-glow
  term; `engine: "spectrl2"` (default, pure Python) vs `engine: "smarts"` (installed here, a
  full 401-point physical spectrum).
- **Good result:** solar zenith, clearness, atmosphere inputs (AOD/PWV/ozone), and CCT/mel-DER
  of the sky. **Measured here** *(Athens June 21 noon):* `atmosphere_from_epw` → `aod500 0.254, pw 2.80 cm, ozone 0.30 atm-cm`; the sky-diffuse spectrum is **CCT ~8568 K, mel-DER 1.14** (blue-rich,
  as a daytime sky should be); solar `zenith 18.8°`, `air-mass 1.06`. With `engine:"smarts"` the spectrum
  gains visible absorption-line structure but agrees with `spectrl2` to **~2%**.
- **Go further:** run the same hour with both engines and compare — SMARTS vs SPECTRL2 usually
  agree to a few percent. (On a machine without SMARTS, `engine:"smarts"` raises by design.)

### 5.3.4 `/mcp__hcl-mcp__import_obj_room` — bring CAD geometry in

- **Argument:** `space_description` (e.g. `4×3 m office, one window`).
- **Files:** `inputs/geometry/office_room.obj` or `office_room_blinds.obj` (or yours). A pinned
  `office_room_material_map.json` ships beside each and is auto-discovered (your own OBJ instead
  gets an auto-generated map from its `.mtl`). These exports are **Z-up** → `up_axis Z`.
- **Tool chain:** `radiance_status` → `import_geometry(dry_run=true)` (shows groups) →
  `import_geometry(derive_sensors=true)` → composes scene + sky → `run_grid`/`run_annual` →
  `circadian_metrics`/`compliance`.
- **Parameters worth knowing:** `dry_run` (discover groups first), `derive_sensors` (auto work-
  plane grid + seated 1.2 m / standing 1.6 m eye points + glare views), `north_angle_deg`
  (critical for daylight), `annotate` (a falsecolor render colored by material).
- **Good result:** it lists your groups, you map them, and it returns a per-channel scene + auto
  sensors + apertures (windows with azimuth/tilt) + a `manifest`.
- **Go further:** keep the returned `geometry_set` / `material_sets` / `observer_sets` /
  `apertures` — every downstream prompt (5.5–5.8) reuses them. Then import the **other** model
  (`office_room_blinds.obj`) and re-run the same daylight grid — that's **Scenario S1** (blinds
  A/B) in [Part 4.5](#part-45--built-in-scenarios-use-what-is-in-the-folder).

#### 5.3.4a — Dedicated sensor tools: `workplane_grid`, `observer_points`, `photosensors`

`import_geometry(derive_sensors=True)` is the quickest path. Three dedicated tools give you more
control — and let you regenerate the shipped `.pts` files at any time (a fourth, `preview_scene`,
lets you see where they all landed — §5.3.4b/c):

**`workplane_grid`** — EN 12464-1 working-plane illuminance grid.

```
workplane_grid {
  "obj_path": "inputs/geometry/office_room.obj",
  "sidecar":  "inputs/geometry/office_room_material_map.json",
  "workplane_h": 0.8,
  "border_offset": 0.25,
  "write_pts": "grid.pts"
}
```

The tool detects the room's interior extent (±2.0 × ±3.5 m on `office_room.obj`, source
`inner_surface`), applies a 0.25 m border offset, and lays a uniform grid at 0.8 m (the EN 12464-1
task-plane height). On `office_room.obj` it produces **45 points** in a 5 × 9 grid (spacing
0.700 m × 0.722 m). Every row is `[x, y, 0.8, 0, 0, 1]` — positions at working-plane height,
up-facing normal. The `methodology` block shows how the cell count and spacing were derived:

| key                      | value (office_room)    |
| ------------------------ | ---------------------- |
| `interior_extent`      | ±2.0 × ±3.5 m       |
| `workplane_z`          | 0.8 m                  |
| `d` (long side)        | 7.0 m                  |
| `p` (EN spacing ratio) | 0.779                  |
| `n_cells`              | x: 5, y: 9 → 45 pts   |
| `spacing`              | x: 0.700 m, y: 0.722 m |

Feed `grid.pts` → `run_grid` for horizontal task illuminance and EN 12464-1 `compliance`.

**Non-rectangular rooms — including concave L/T/U shapes.** `workplane_grid` now clips to the real
floor and covers non-rectangular rooms end-to-end. Two new params: `clip_to_footprint` (default
`true`) clips the grid to the true floor polygon (off-floor cells dropped) instead of the bounding
box, and `footprint_border` insets that clip by an extra margin. On a **concave** room (L/T/U),
inner-wall detection can degenerate (there's no single well-defined "interior offset" once the room
has a notch) — when that happens, the interior falls back to the floor **bounding box**, which is
then **polygon-clipped**, so the grid still spans the whole shape rather than missing an arm of the
L. `interior_extent_source` reads `"footprint_bbox"` on that fallback (with a warning), and
`methodology` gains `clipped{kept,dropped,footprint_source,footprint_border}`. A plain rectangular
room is unaffected — `office_room.obj` still returns the same **45 byte-identical points**. Live
numbers from the feature's own verification: office (rectangular) = 45 pts; an L-shaped room = **48
cells, 16 dropped**, both arms of the L covered. **Known limitation:** the EN border is enforced
along the interior bounding box, not along the concave (notch) walls themselves — raise
`footprint_border` if you need every edge inset.

**`observer_points`** — workstation eye sensors.

```
observer_points {
  "obj_path": "inputs/geometry/office_room.obj",
  "sidecar":  "inputs/geometry/office_room_material_map.json",
  "eye_height": 1.2,
  "direction_fallback": "window",
  "write_pts": "observers.pts"
}
```

The tool scans OBJ object names for seat ↔ screen pairs (default patterns `chair.*seat|seat` and
`disp.*panel|screen|monitor|display`). On `office_room.obj` it finds **2 workstations**:

| workstation                  | eye position       | gaze direction | source          |
| ---------------------------- | ------------------ | -------------- | --------------- |
| Chair_Seat_1 ↔ Disp_Panel_1 | (1.75, −1.2, 1.2) | (−1, 0, 0)    | `workstation` |
| Chair_Seat_2 ↔ Disp_Panel_2 | (−1.75, 1.2, 1.2) | (1, 0, 0)      | `workstation` |

If no screen is paired, the gaze falls back to `direction_fallback`:

- `"window"` — toward the glazing centroid (default; useful for circadian mel-EDI).
- `"azimuth"` — fixed compass bearing via `fallback_azimuth`.
- `"sweep"` — `sweep_n` rotated views at one eye point (covers all directions).
  If no seats are found at all, a single sensor is placed at `position_fallback="room_center"`.

`eye_height` accepts a list (e.g. `[1.2, 1.6]`) to place dual-height sensors per workstation.

The `glare_views` in the response are ready-made fisheye strings:
`-vp 1.75 -1.2 1.2 -vd -1 0 0 -vta -vh 180 -vv 180` — paste one straight into `glare_ugr`.
Feed `observer_1.pts` / `observer_2.pts` → `run_grid`/`run_annual` for vertical mel-EDI, and
`glare_views` → `glare_ugr` for DGP/UGR at each workstation.

`observer_points` also takes `clip_to_footprint` (default `true`), a **footprint check**: it
**reports** (warns) any observer whose eye point falls outside the room's floor footprint, but it
does **not** move the observer — observers stay furniture-anchored (a chair/screen pairing is
ground truth, not the floor polygon). `methodology` gains `footprint_checked`. On `office_room.obj`
both workstations are interior, so you should see `footprint_checked:true` with no warnings.

**`photosensors`** — daylight-dimming reference sensors (pure-Python, no Radiance; methodology.md
§3). This is the third dedicated sensor tool: instead of a work-plane grid or workstation eyes, it
places the sensors a daylight-linked dimming *control system* actually reads.

```
photosensors {
  "obj_path": "inputs/geometry/office_room.obj",
  "sidecar":  "inputs/geometry/office_room_material_map.json",
  "zone_rule": "head_height",
  "sensor_fraction": 0.667,
  "mount": "workplane",
  "workplane_h": 0.8,
  "write_pts": "photosensors.pts"
}
```

It locates the dominant glazed facade, builds window-head-height sidelighting zones (`zone_rule`
`"head_height"` default, or `"ies_2.5"`), and places **one horizontal sensor per zone** at
`sensor_fraction` (default 2/3) of the zone's depth, centred on the facade and clipped to the
floor. `mount` is `"workplane"` (up-facing, at `z = floor + workplane_h`) or `"ceiling"`
(down-facing, at `z = ceiling − ε`). The **inward** direction is derived from the room centroid
(floor_centroid − glazing_centroid), **not** the glass face normal — normal winding isn't reliable
across CAD exports. It requires a floor **and** a glass group in the OBJ (else a clean
`ValueError`). On the south `office_room.obj` it produces `sensor_1≈(0, -1.8467, 0.80)` (near the south
facade) / `sensor_2≈(0, 0.6333, 0.80)` (deeper) — 2 zone sensors. Feed the resulting `.pts` (shipped as
`sensor_1.pts`/`sensor_2.pts`) → `run_grid`/`run_annual` to drive daylight-linked dimming control
logic.

> **Selector note.** Five `.pts` ship in `inputs/sensors/` (`office_room_grid.pts`, `observer_1.pts`,
> `observer_2.pts`, `sensor_1.pts`, `sensor_2.pts`) — all for the single-window south `office_room.obj`.
> The `"points":"auto"` entry in `active_inputs.json` expects a single match — with five files present it is
> ambiguous. The tools above always *regenerate* from the OBJ (and are required for the other three models),
> so you can just call them. For explicit downstream runs, pass the path directly:
> `"points":"inputs/sensors/office_room_grid.pts"` for the work-plane grid,
> `"points":"inputs/sensors/observer_1.pts"` for a workstation eye run, or
> `"points":"inputs/sensors/sensor_1.pts"` for a daylight-dimming photosensor.

#### 5.3.4b — `/mcp__hcl-mcp__place_sensors` — orchestrate all sensor tools conversationally

The `place_sensors` prompt drives `workplane_grid`, `observer_points`, `photosensors`, and
`preview_scene` together in one guided conversation:

1. **Confirm geometry** — it reads the OBJ dry-run to show you the groups and bounding box.
2. **Run `workplane_grid`** — shows the EN 12464-1 math (d, p, grid count, spacing) and writes
   `grid.pts`. Ready to hand to `run_grid`.
3. **Run `observer_points`** — shows detected workstations (or which fallback applies) and writes
   `observer_1.pts` / `observer_2.pts`. The `glare_views` strings are ready for `glare_ugr`.
4. **Run `photosensors`** — a daylight-photosensor step: derives the facade + sidelighting zones
   and writes `sensor_1.pts` / `sensor_2.pts` for daylight-linked dimming.
5. **Run `preview_scene`** — a final visual placement check: renders all the point sets it just
   generated onto plan + 3D matplotlib PNGs so you can eyeball that the grid, observers, and
   photosensors landed where expected before running anything downstream.
6. **Hand off** — suggests the next calls: `grid.pts` → `run_grid` (task lux + EN 12464-1),
   observer `.pts` + `glare_views` → `run_grid`/`glare_ugr` (mel-EDI + DGP per workstation), and
   `sensor_*.pts` → `run_grid`/`run_annual` (daylight-linked dimming).

Invoke it with:

> `/mcp__hcl-mcp__place_sensors`

#### 5.3.4c — `/mcp__hcl-mcp__visualize_scene` — guided PNG preview flow

A focused prompt around just the diagnostic preview, for when you only want to *see* where the
sensors/luminaires landed rather than run the full sensor-placement conversation:

1. **Ensure geometry** — confirms an OBJ + material map are available (imports/generates one if not).
2. **Generate or locate points** — reuses (or generates) `grid.pts` / `observer_*.pts` /
   `sensor_*.pts`.
3. **Run `preview_scene(render="all", …)`** — renders the plan (top-down) and 3D PNGs over
   whichever point sets + luminaire groups are available.
4. **Report `image_paths`** — hands back the two file paths and reminds you these are **diagnostic
   overlays for placement verification, not a photometric render** (that's `run_image`).

Invoke it with:

> `/mcp__hcl-mcp__visualize_scene`

**`preview_scene`** itself (matplotlib PNG, `Agg` backend — requires matplotlib; still no Radiance
binary): renders the TRUE floor polygon (a non-rectangular room shows its real outline, never a
hardcoded rectangle) plus whichever point layers you pass, in a plan (top-down) view and a real
`mplot3d` 3D view (not isometric) that also draws the window and ceiling luminaires as true 3D
geometry. It works in the post-north final frame, so it lines up with already-rotated `.pts` files.

```
preview_scene {
  "obj_path": "inputs/geometry/office_room.obj",
  "sidecar":  "inputs/geometry/office_room_material_map.json",
  "render": "all",
  "grid_pts": "inputs/sensors/office_room_grid.pts",
  "observer_pts": ["inputs/sensors/observer_1.pts", "inputs/sensors/observer_2.pts"],
  "photosensor_pts": ["inputs/sensors/sensor_1.pts", "inputs/sensors/sensor_2.pts"],
  "write_prefix": "preview"
}
```

`render` is `"all"` (default; writes both views), or `"grid"`/`"observers"`/`"observers_3d"` for
just one layer/view. `grid_pts`/`observer_pts`/`photosensor_pts` each accept a `.pts` path **or**
inline `[x,y,z,dx,dy,dz]` rows — pass `None` to omit a layer. `luminaire_groups` names OBJ object
groups to draw as fixture geometry (footprints in plan; true ceiling geometry in 3D). `render="all"`
writes two files: `<write_prefix>_all_plan.png` + `<write_prefix>_all_3d.png` (regenerate on demand —
the pre-built overlays no longer ship). Legend: grid = orange dots, photosensors = green
diamonds, observers = red dots + arrows, luminaires = yellow squares, window = cyan, footprint =
grey outline. An unknown `render` value warns and falls back to `"all"`; an empty layer warns
rather than silently vanishing.

> **Honesty note.** `preview_scene` is a schematic **diagnostic** — it verifies *where* things are,
> not *how much light* is there. For actual photometric renders use `run_image` (Radiance `rpict`).

### 5.3.5 `/mcp__hcl-mcp__hcl_grid_study` — daylight at one moment

- **Argument:** `space_description`.
- **Files:** geometry (from 5.4) + materials, surface/glass reflectances, a date/time/place.
- **Work-plane points:** the grid passed to `run_grid` can come from `workplane_grid` (`grid.pts`) — see §5.3.4a.
- **Tool chain:** `import_geometry` (or `write_material`) → `colored_sky` → `run_grid` →
  `circadian_metrics` → `compliance`.
- **Parameters worth knowing:** `colored_sky` needs `month/day/hour/lat/lon/utc` and irradiance
  (`direct`/`diffuse` in W, `irrad_mode:"W"`); `run_grid` takes `export_csv` to dump the per-
  point table.
- **Good result:** per-point photopic + melanopic-EDI at the eye, and pass/fail.
- **Go further:** export the CSV and compare seated (1.2 m) vs standing (1.6 m) eye heights —
  melanopic light at the eye changes a lot with where you look.

### 5.3.6 `/mcp__hcl-mcp__fisheye_eye_analysis` — what the eye sees / glare

- **Argument:** `view_description` (or reuse a `glare_views` string from the import).
- **Eye points + glare views:** `observer_points` (§5.3.4a) emits both `observer_*.pts` and ready-made `glare_views` fisheye strings for this prompt.
- **Files:** a scene (from 5.4 / 5.5).
- **Tool chain:** `run_image` with `fov_weighting` → cosine-weighted RGB eye irradiance →
  `compliance`.
- **Parameters worth knowing:** `view` (default `-vta -vh 180 -vv 180` = a 180° fisheye),
  `fov_weighting:true` (applies the ipRGC field-of-view weighting), `x`/`y` (resolution).
- **Good result:** fisheye HDR maps (photopic/melanopic/neuropic) and mel-EDI at the eye. Note:
  this path uses the channel_type=1 ×179 conversion and does **not** re-run `circadian_metrics`
  (to avoid double-counting).
- **Go further:** also call `glare_ugr` on the same scene+view to get UGR/DGP and the glare-
  source list, so you see brightness *and* discomfort together.

### 5.3.7 `/mcp__hcl-mcp__electric_lighting_design` — electric + daylight + energy

- **Argument:** `space_description`.
- **Files:** an IES (`inputs/luminaires/L09_neutral.ies` — or `L09_warm`/`L09_cool`), geometry + materials, a sky/
  location, and a target (EN 12464-1 task + circadian target).
- **Tool chain:** `ies_analyze` → `ies_to_radiance` → `run_grid` (+ `electric_lights`) →
  `daylight_savings` → `compliance`.
- **Parameters worth knowing:** `ies_to_radiance.placement` (a grid of fixtures:
  `{"grid":{rows,cols,row_spacing,col_spacing,origin}}`), `multiplier` × `maintenance_factor`;
  `daylight_savings.mode` (`point_in_time` here).
- **Getting the *combined* grid (`run_grid` with electric added).** `run_grid` only adds the
  `electric`/`combined`/`total_wattage` keys when you pass it an **`electric_lights`** payload — a list
  like `[{"ies":…, "placement":{"positions":[{"xyz":[x,y,z]}, …]}, "spd":…, "multiplier":1.0, "maintenance_factor":0.8}]`. Two ways to get it: **(a)** add a `type:"luminaire"` group to your OBJ —
  a `g <name>` with `p` point markers at the fixture positions — and map it to
  `{"type":"luminaire","ies":…,"spd":…}`; `import_geometry` then returns a ready `electric_lights` you
  hand straight to `run_grid`. **(b)** Build that list by hand and pass it directly (no OBJ edit). The
  shipped `office_room.obj` has **no luminaire group**, so out of the box you get the daylight grid plus
  the `ies_analyze`/spectrum comparison — add the group (or the payload) to see daylight+electric combined.
- **Good result:** required-vs-achieved illuminance, glare (UGR), energy saved (kWh/m²), and the
  melanopic dose. *(Verified pieces on a fully-engined machine: `ies_analyze` 4702 lm / 123.7 lm·W⁻¹,
  LOR≈1.0; `ies_to_radiance` runs `ies2rad -m 0.8`; `lighting_controls` ~87% reduction when daylight
  exceeds the setpoint; `daylight_savings` daylight-lux matches `run_grid` photopic.)*
- **Go further:** run `recommend_fixtures` first to get a starting layout, then feed its count/
  spacing into `ies_to_radiance.placement` and verify with the real IES. Re-run the whole chain
  with `L09_warm.ies` then `L09_cool.ies` (paired with their `L09_*.spd`) to see required-lux held
  constant while mel-EDI swings with CCT — **Scenario S3** in
  [Part 4.5](#part-45--built-in-scenarios-use-what-is-in-the-folder).

### 5.3.8 `/mcp__hcl-mcp__annual_circadian_dose` — a whole year of daylight

- **Argument:** `space_description`.
- **Files:** weather (`inputs/weather/GRC_Athens.167160_IWEC.wea`, auto-derived), geometry, observer points, and a
  **tight** `period` like `[[6,21,8],[6,21,18]]`.
- **Tool chain:** `weather` → `run_annual` (2-phase DDS) → recombine to annual mel-EDI / hours-
  above-threshold.
- **Parameters worth knowing:** `period` (keep it small!), `dosimetry_threshold` (default 250
  mel-EDI), `eye_sensor` index.
- **Good result:** timestep count and a dosimetry summary.
- **Reading `dosimetry.hours_above` (fixed 2026-07-25 — ADR-0001/ADR-0003).** It is scored on CIE S 026
  **mel-EDI**, and each timestep contributes its **own** duration (from `timestep_min`). Both were defects
  until that date, and a tight `period` like the one above is exactly where they bit: the old code fed
  `melanopic_lux` (≈1.0997× larger, so the threshold was effectively relaxed to ~227 lx) and charged the last
  sample of each day the whole overnight gap — a 3-day 08:00–18:00 window read **59 h instead of 33 h**, and a
  multi-month window read **1475 h instead of 33 h**. Sanity-check any dosimetry number against
  `n_timesteps × (timestep_min/60)`: `hours_above` can never exceed it. Figures captured before 2026-07-25
  must be **recomputed, not rescaled** — the threshold comparison is non-linear.
- **Go further:** **this one is slow** — start with one or two hours.

### 5.3.8a `/mcp__hcl-mcp__annual_daylight_study` — climate-based daylight metrics (DA/UDI/DF/sDA/ASE)

- **What it's for (plain English):** the standard green-building daylight scores that answer *"does
  this room get enough daylight over the year, and not too much harsh sun?"* — the ones **LEED** and
  **EN 17037** ask for. The five acronyms (each defined in full in [§6.3](#63-annual-daylight-the-2-phase-method)):
  **DA** = share of work hours a desk has enough daylight; **UDI** = the same, split into *too dark /
  useful / too bright*; **sDA** = share of the room that passes DA; **ASE** = share of the room hit by
  too much **direct sun** (a glare/overheating warning); **DF** = the classic "Daylight Factor" —
  indoor vs outdoor light under a dull overcast sky. (This is the daylight your **eyes** care about; the
  body-clock version is prompt 5.8, `annual_circadian_dose`.)
- **Argument:** `space_description`.
- **Files:** weather (`inputs/weather/GRC_Athens.167160_IWEC.wea`, auto-derived), geometry, and a grid
  of measurement points on the desks/floor (**auto-derived from the room**, or make one once with the
  `sensors` tool and reuse it by name — see below).
- **Tool chain:** `sensors` (save a named grid) → `annual_daylight` (the DA/UDI/sDA/ASE scores) →
  `daylight_factor` (the DF %) → `daylight_savings` (how much lighting energy the daylight saves).
  Every tool accepts `sensor_set="<name>"` so you list the grid **once** and reuse it.
- **Parameters worth knowing:** the pass/fail thresholds, all overridable — `da_threshold` (300 lx =
  "enough light"), the UDI bin edges `udi_lower/udi_sup/udi_aut` (100/300/3000 lx), `sda_da_fraction`
  (0.5 → the standard **sDA300/50%**), `ase_threshold`/`ase_hours` (direct sun over 1000 lx for more
  than 250 hours), and the working day (`occupied_start`/`occupied_end`, default 08:00–18:00). **ASE is
  measured from direct sunbeams only** (it ignores light bounced off walls — the `-ab 0` Radiance
  setting), so it's a *separate* calculation from DA/UDI, which use the full bounced daylight. Don't
  compare the two numbers as if they came from the same run.
- **Good result:** a per-desk table (DA / UDI bins) plus whole-room rollups (sDA, ASE) you grade
  against **LEED v4 EQ "Daylight"** / **EN 17037**, plus a DF % for a quick sun-free sanity check.
- **Go further:** like every year-long run this is **slow** — it simulates all 8760 hours (there's no
  short-period option yet), so try a small room first. Define the grid **once** with `sensors` and
  reuse it across all three tools rather than re-typing the points each time.

### 5.3.9 `/mcp__hcl-mcp__annual_alertness` — year-long alertness, nvRD (Daysim live)

- **Argument:** `space_description`.
- **Files:** the EPW, one sensor point + a view direction.
- **Tool chain:** `daysim_status` → `generate_subhourly_wea` → `annual_nvrd`.
- **Parameters worth knowing:** `timestep_min` — keep the **default 6** (6 min). The Daysim
  sub-hourly step must be one of `{1,2,3,4,5,6,10,12,15,20,30}` and **60 is rejected**; the nvRD
  model itself needs a step ≤ 0.3 h, so **don't exceed 15** (20/30 raise downstream).
  `point_xyz` + `view_vec` (one orientation per run); `physical_sky` (opt-in EPW-shaped spectra)
  + `engine`.
- **Good result:** Daysim runs live here, writing a sub-hourly `.wea` and running the full
  2-phase DDS transport. Output is `R_D` (relative alerting response), `cumulative`, and a
  faithful-vs-enhanced divergence.
- **Go further:** remember `R_D` is **relative**, not absolute — compare two designs/orientations,
  don't read it as an absolute dose.

### 5.3.10 `/mcp__hcl-mcp__hcl_studio` — the full guided study (the front door)

- **Arguments:** `space_description`, `daylight_aware` (`true`/`false`).
- **Files:** room dims/reflectances + a mel-EDI target (required); optionally a CAD `.obj`, a
  real IES, and weather (for the annual part). Pick a short study slug like `athens_office`.
- **Tool chain:** the complete journey with a **resumable brief** — orient (`validate`/
  `radiance_status`/`daysim_status`) → goal → space (optional `import_geometry`) → daylight
  baseline → `recommend_fixtures` → `ies_analyze`/`ies_to_radiance` → `run_grid` (+`run_annual`/
  `annual_nvrd`) → `daylight_savings` → `build_report`, with `save_brief`/`load_brief` at each
  phase.
- **Good result:** `report.md` + `report.html` under the work dir with goal recap, fixture spec,
  target-vs-achieved pass/fail, circadian↔glare cross-check, and compliance. **The best single
  start-to-finish demo.**
- **Go further:** because it saves a brief after each phase, you can stop and resume later with
  the same study slug — or re-run just the report after editing the brief.

> Tip: mix modes. Run `hcl_studio` for the journey, then fire a focused prompt (5.2, 5.3, 5.7)
> to inspect one piece in depth.

---

## 5.4 — The 46 tools, grouped

You can call any of these directly ("Call `<tool>` with …") instead of going through a prompt.
4 of the 50 entries are nicknames: `run_validation`=`validate`, `get_reference`=`reference`,
`list_presets`=`presets`, `import_weather`=`weather`.

> The tables below list each tool's **key** inputs (the ones you set most often). For the
> **complete** signature of every tool — *every* parameter, its default, and what each choice
> does — see **[Appendix B — Complete parameter reference](#b--complete-parameter-reference-every-tool-every-option)**.
> If you ever wonder "what else can this tool take?", that appendix is the answer.

### A. Spectral core — pure math, no files, instant

| Tool                     | What it does                                    | Key inputs                                                                                                                                        | Key outputs                                                                                                                                                                                       |
| ------------------------ | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `validate`             | built-in correctness self-test                  | —                                                                                                                                                | `ok`, `checks[]`                                                                                                                                                                              |
| `presets`              | list/fetch standard illuminants                 | `name` (D65, D50, A, FL1–12, LED_3000K/4000K/5000K/BLUEPUMP/VIOLETPUMP)                                                                        | `spd` (401 pairs) + `meta`                                                                                                                                                                    |
| `spd_to_channels`      | bin a spectrum into channels                    | `spd` (`.spd` path, text, or list of `[wl,val]`), `channel_type`                                                                          | `channels` (9 or 3)                                                                                                                                                                             |
| `alpha_opic`           | CIE S 026 α-opic E/ELR/EDI                     | `spd` **or** `channels`; `alpha` (1=S,2=M,3=L,4=rhod,5=mel; omit=all)                                                                 | per-α`{E,ELR,EDI}`; `scale_warning`                                                                                                                                                          |
| `circadian_metrics`    | equivalent illuminances                         | `channels`, `channel_type`, `spd` (optional — makes mel-DER exact)                                                                                                                    | `photopic_lux`, `melanopic_lux`, `neuropic_lux`, **`mel_edi`**, `mel_der`, `mel_der_source` — **feed `mel_edi`, not `melanopic_lux`, to `compliance`** (~9% apart; enough to flip a verdict) |
| `spectral_metrics`     | derived HCL quantities                          | `spd` **or** `eml_edi_value`                                                                                                            | `cct_duv`, `mel_der`, `mel_photopic_ratio`, `eml_edi`                                                                                                                                     |
| `compliance`           | judge vs a standard                             | `mel_edi`/`eml`, `standard` (6: brown_2022, well_v2_l03, iso_cie_8995_1_2025, en_17037, en_12464_1, ul_24480), `period`, `daylight_met` | verdict + threshold + citation —**shape varies:** brown/iso → pass/fail · WELL → `result_points` · en_17037 → n/a · ul_24480 → unsupported · en_12464_1 → electric task (5.3.2) |
| `reconstruct_spectrum` | rebuild a 401-pt spectrum from sky+sun channels | `sky_channels`, `sun_channels`, `method` (`faithful`/`reference`), `solar_zenith`                                                     | `spectrum`, `divergence`                                                                                                                                                                      |
| `reference`            | look up HCL reference content                   | `topic` (bins/coefficients/caveats/overview)                                                                                                    | reference text                                                                                                                                                                                    |

### B. Geometry, materials, sky

| Tool                     | What it does                                                     | Key inputs                                                                                                                                                                                                                                    | Key outputs                                                                                                                                                   |
| ------------------------ | ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `import_geometry`      | OBJ → per-channel Radiance scene                                | `obj_path`, `material_map`, `dry_run`, `derive_sensors`, `units`, `up_axis`, `north_angle_deg`, `annotate`, `sidecar`                                                                                                       | `geometry_set`, `material_sets`, `apertures`, `grid_points`, `observer_sets`, `glare_views`, `ground_albedo`, `electric_lights`, `manifest` |
| `check_geometry`       | tier-1 geometry health audit, standalone (no Radiance call)     | `obj_path`, `material_map` or `sidecar`, `units` (**load-bearing** — every tolerance is absolute metres), `up_axis`, `sensors`, `photosensors`, `electric_lights` | `{ok, counts, findings, checked, skipped, confidence}` — a **report**, never an exception on a parseable OBJ (only `import_geometry(strict=true)` raises) |
| `workplane_grid`       | EN 12464-1 work-plane grid from OBJ, incl. concave (L/T/U) rooms | `obj_path`, `material_map` or `sidecar`, `workplane_h` (0.8), `border_offset` (0.25), `max_spacing`, `clip_to_footprint` (true), `footprint_border`, `write_pts`                                                            | `points`, `methodology` (interior extent, n_cells, spacing, `clipped{kept,dropped,footprint_source,footprint_border}`, …), `pts_path`                |
| `observer_points`      | workstation eye sensors from OBJ                                 | `obj_path`, `material_map` or `sidecar`, `eye_height` (1.2, or list), `seat_pattern`, `screen_pattern`, `direction_fallback` (`window`/`azimuth`/`sweep`), `clip_to_footprint` (true), `write_pts`                    | `observers[]` (eye, direction, source, seat/screen objects), `glare_views`, `pts_path`, `methodology` (incl. `footprint_checked`)                   |
| `photosensors`         | daylight-dimming reference sensors from OBJ (pure Python)        | `obj_path`, `material_map` or `sidecar`, `zone_rule` (`head_height`/`ies_2.5`), `depth_factors`, `sensor_fraction` (2/3), `mount` (`workplane`/`ceiling`), `workplane_h`, `write_pts`                               | `points`, `methodology{facade, zones[], zone_rule, sensor_fraction, mount, count}`, `pts_path`, `assumptions`, `warnings`                           |
| `preview_scene`        | matplotlib PNG scene previews (diagnostic, not photometric)      | `obj_path`, `material_map` or `sidecar`, `render` (`all`/`grid`/`observers`/`observers_3d`), `grid_pts`, `observer_pts`, `photosensor_pts` (each a`.pts` path or inline rows), `luminaire_groups`, `write_prefix` | `image_paths`, `format`, `render`, `layers{name:count}`, `warnings`                                                                                 |
| `sensors`              | manage named persistent sensor sets                              | `action` (`create`/`list`/`get`/`delete`), `name`, `points` **or** `grid={interior,floor_z,workplane_h?,max_spacing?}`, `overwrite`                                                                                   | `path`, `count`, `source`, `points` — reuse across `annual_daylight`/`daylight_factor`/`daylight_savings` via `sensor_set="name"`            |
| `write_material`       | author a material`.rad`                                        | `channels`, `material_type` (0=glass,1=plastic), `channel_type`, `name`, `roughness`, `specularity`                                                                                                                               | `files`, `channel_output`                                                                                                                                 |
| `glass_transmissivity` | glazing transmittance → transmissivity                          | `transmittance` (number or list)                                                                                                                                                                                                            | `transmissivity`                                                                                                                                            |
| `colored_sky`          | colored Perez sky+sun definition                                 | `diffuse_channels`, `direct_channels`, `month/day/hour`, `lat/lon/utc`, `irrad_mode`, `direct`/`diffuse`                                                                                                                        | `files`, `sky_defs`                                                                                                                                       |
| `colored_luminaire`    | inject a channel triplet into a luminaire`.rad`                | `rad_path`, `channels9`, `count` (0=blue,1=green,2=red)                                                                                                                                                                                 | `file`, `rad`                                                                                                                                             |

### C. Simulation — grid, image, glare

| Tool                | What it does                        | Key inputs                                                                               | Key outputs                                        |
| ------------------- | ----------------------------------- | ---------------------------------------------------------------------------------------- | -------------------------------------------------- |
| `run_grid`        | point-in-time grid metrics (rtrace) | `scene_sets`, `points`, `channel_type`, `electric_lights`, `export_csv`        | `n_points`, `daylight.metrics[]`, `csv_path` |
| `run_image`       | fisheye HCL image (rpict)           | `scene_sets`, `view`, `fov_weighting`, `glare`, `x`/`y`, `electric_lights` | `maps` (.hdr), `rgb_values_file`               |
| `glare_ugr`       | render + evalglare → UGR/DGP       | `scene_sets`, `view`, `channel_type` (default 0)                                   | `glare{UGR,DGP,glare_sources}`                   |
| `radiance_status` | is Radiance available?              | —                                                                                       | `available`, `version`, `found`, `missing` |
| `quality_presets` | the accuracy/runtime trade-off, by name | `level` (optional: `low`/`medium`/`high`/`extra_high`; omit for the whole table)                | per level: `rad_params`, `use_for`, **`caveat`**, `relative_cost`. Pass the level as `quality=` to any of the eight simulation tools; an explicit `rad_params` always wins. **`low` is `-ab 0`** — no interreflection, so DA/sDA/UDI are meaningless there while ASE stays exact. |

### D. Electric lighting & energy

| Tool                   | What it does                                 | Key inputs                                                                                                                                                                          | Key outputs                                                                                     |
| ---------------------- | -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `ies_analyze`        | parse an IES photometric report              | `ies` (text or path)                                                                                                                                                              | `max_candela`, `photometric_type`, `total_flux`, `efficacy`, `LOR`, beam/field angles |
| `ies_to_radiance`    | IES →`.rad` (ies2rad), optional placement | `ies`, `placement`, `multiplier`, `maintenance_factor`, `color`                                                                                                           | `outputs` (`_placed.rad`)                                                                   |
| `recommend_fixtures` | first-principles fixture sizing              | `length_m`, `width_m`, `height_m`, `mount_height_m`, `target_em_lux`, `target_mel_edi`, `distribution`                                                                | `fixture_count`, `layout`, `target_cct_band`, `binding_constraint`, caveats             |
| `lighting_controls`  | daylight-dimming savings calc                | `itot_per_point` **or** `itot_series`+`area`, `weights`, `iset`, `p_rated`, `control_type`                                                                      | `FP`, `P_elec`, `P_saved`, `reduction` (or annual kWh)                                  |
| `daylight_savings`   | run a daylight sim → controls               | `mode` (`point_in_time`/`annual`), `scene_sets`/`channel_scenes`, `points` **or** `sensor_set`, `wea`, `weights` (one floor-area fraction per point, Σ≤1) | `daylight_lux`, `controls{}` — `mode="annual"` supports a multi-point grid + annual kWh  |

> ⚠️ `recommend_fixtures` sizing and its surface library are **illustrative / first-principles**,
> not measured — treat the numbers as plausibility checks, then verify with a real IES.

### E. Weather, annual & alertness

| Tool                       | What it does                                            | Key inputs                                                                                                                                                                                  | Key outputs                                                                       |
| -------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `weather`                | ingest`.wea` / subset a period                        | `wea_path`, `period`, `subset_out`, `timestep_min`                                                                                                                                  | `wea_summary`, `decomposed{HOY,wea_lines}`, `subset_wea`                    |
| `run_annual`             | annual 2-phase DDS → mel-EDI + dosimetry               | `channel_scenes`, `wea`, `points`, `period`, `dosimetry_threshold`                                                                                                                | `n_timesteps`, `metrics[]`, `dosimetry{}`                                   |
| `nvrd`                   | alerting response from a spectral time series           | `spectral_series` (per-step rows of 311 or 401 values — **pass a file path** for full-res rows; big inline arrays can truncate over the wire), `timestep_h` (≤0.3, default 0.1) | `effective_irradiance`, `relative_response`, `cumulative_response`          |
| `daysim_status`          | is Daysim available?                                    | —                                                                                                                                                                                          | `available`, `version`, `found`, `missing`                                |
| `build_daysim`           | build Daysim from source                                | `run`                                                                                                                                                                                     | command plan /`bin_dir`                                                         |
| `generate_subhourly_wea` | EPW → sub-hourly`.wea` (Daysim)                      | `epw`, `timestep_min` (6)                                                                                                                                                               | `.hea`, `.wea`, commands                                                      |
| `annual_nvrd`            | annual alertness straight from weather                  | `point_xyz`, `view_vec`, `epw`, `channel_scenes`, `points`, `timestep_min`                                                                                                      | `faithful`/`enhanced` `{R_D,RD_cum}`, divergence                            |

> The annual/alertness tools are **long-running**. Always pass a tight `period` (annual) and
> remember `timestep_min` ∈ `{1,2,3,4,5,6,10,12,15,20,30}` for the Daysim ones — 60 is rejected,
> and the nvRD path needs ≤ 15 (the default 6 is the safe choice).
> `R_D` is **relative**.

### E-bis. Climate-based daylight metrics (DA / UDI / DF / sDA / ASE)

| Tool                | What it does                                        | Key inputs                                                                                                                                                                                                                                                  | Key outputs                                                                                       |
| ------------------- | --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `annual_daylight` | annual per-point DA/cDA/UDI + spatial sDA/ASE       | `channel_scenes`, `wea`, `points` **or** `sensor_set`, `quality` (`low`/`medium`/`high`/`extra_high`) **or** `rad_params`, `da_threshold` (300), `udi_lower/sup/aut` (100/300/3000), `sda_da_fraction` (0.5), `ase_threshold`/`ase_hours` (1000/250), `occupancy`/`occupied_start`/`occupied_end` | `n_points`, `n_timesteps`, `metrics{per_point[{DA,cDA,UDI_*}], spatial{sDA,DA_avg,ASE,…}}`, plus `rad_params` and — when the ambient settings are preview-grade — **`convergence_warning`**. **Read the warning before quoting sDA/UDI:** they are threshold crossings, so coarse indirect sampling moves them far more than it moves means. ASE is never flagged (its `-ab 0` pass is unaffected). |
| `daylight_factor` | Daylight Factor % under a CIE Standard Overcast Sky | `scene_sets`, `points` **or** `sensor_set`, `month/day/hour`, `gnd_refl`                                                                                                                                                                    | `df_per_point`, `df_avg`, `df_min`, `uniformity`, `e_outdoor`                           |

> **ASE is measured from direct sunbeams only** (bounced light switched off — the `-ab 0` flag),
> while DA/UDI use the full bounced daylight — so the two come from *separate* runs; don't mix them.
> `annual_daylight` always simulates the **full 8760 h** (no short-period option yet). Grade
> `sDA300/50%` + `ASE1000,250h` against **LEED v4 / EN 17037**; DF is the quick sun-free companion.
> Define the grid once with the `sensors` tool (group B) and reuse it by name. This is the daylight
> your **eyes** care about; `run_annual` (group E) is the **body-clock** version.
>
> **Choose the accuracy level deliberately.** Passing no `quality`/`rad_params` inherits a
> preview-grade default *by not choosing* — which on a validated annual run returned **sDA 77.78%**
> where a converged solve returned **100.00%** on identical geometry. Call `quality_presets` for the
> table and pass `quality="high"` for anything you intend to report. If the result comes back with a
> `convergence_warning`, the sDA/UDI numbers in it are sampling-limited: raise the level before
> quoting them.

### F. Physical spectral sky from EPW

| Tool                      | What it does                                        | Key inputs                                                                         | Key outputs                                                                            |
| ------------------------- | --------------------------------------------------- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `atmosphere_from_epw`   | derive atmospheric state for an EPW hour            | `epw`, `month`, `day`, `hour`; opt-in `ozone_mode`/`aerosol_g`/`aod_anchor_nm` | `aod500`, `pw_cm`, `ozone_atm_cm`, `pressure_mbar`, `albedo`, `aerosol_g`, `provenance` |
| `spectral_sky_from_epw` | 1-nm direct + sky-diffuse spectrum                  | `epw`, `month/day/hour`, `engine`, `surface_tilt_deg`, `spectral_albedo`; opt-in `ozone_mode`/`aerosol_g`/`aod_anchor_nm`/`smarts_aerosol` | `direct_normal` (401), `sky_diffuse_horizontal` (401), `geometry`, `ground`    |
| `spectral_epw`          | emit spectral-sky artifacts over the year/`hours` | `epw`, `forms` ⊆ `{spd_set,band_matrix,spectral_wea,sidecar}`, `hours`; opt-in `ozone_mode`/`aerosol_g`/`aod_anchor_nm`/`smarts_aerosol`    | `files{…}`, `n_records`                                                           |
| `spectral_sky_native`   | native Radiance 6.x gensdaymtx (20-band)            | `epw`, `mf`, `mode`, `timeout`                                             | `smx`, `header{ncomp:20}`, `ok`/`timed_out`                                    |

> `spectral_sky_native` and `spectral_epw` over a full year are slow (gensdaymtx processes every
> hour). Trim the EPW or pass `hours`/`timeout`. `engine:"smarts"` works here (SMARTS installed).

### G. Study brief & report

| Tool             | What it does                        | Key inputs           | Key outputs                      |
| ---------------- | ----------------------------------- | -------------------- | -------------------------------- |
| `load_brief`   | load (or start) a study brief       | `study`            | brief (empty skeleton first run) |
| `save_brief`   | shallow-merge-save the brief        | `study`, `brief` | `saved`, `path`              |
| `build_report` | render brief →`report.{md,html}` | `study`, `brief` | `md_path`, `html_path`       |

---

## 5.5 — The 14 resources

Resources are reference docs/data the assistant reads on demand. Ask, e.g.:
*"Read the hcl-mcp resource `hcl://index`."*

**Catalog (read this first):**

- `hcl://index` — a self-describing catalog of all 14, including valid template argument values.

**Fixed reference docs (10):**

- `hcl://reference/coefficients` — photopic/melanopic/neuropic weighting vectors (3- & 9-channel).
- `hcl://reference/bins` — the wavelength bins for 3- & 9-channel.
- `hcl://reference/ies` — IESNA LM-63 field guide.
- `hcl://reference/lighting-controls` — EnergyPlus §7.3.5 dimming equations.
- `hcl://reference/daysim` — Daysim build & I/O reference.
- `hcl://reference/nvrd-bridge` — how the annual sim bridges to nvRD + caveats.
- `hcl://reference/geometry` — the `import_geometry` contract (types, material specs), plus `photosensors`, `preview_scene`, and footprint clipping.
- `hcl://reference/caveats` — the §9.3 source-port caveats (read this to know the limits).
- `hcl://reference/glossary` — metric/unit glossary.
- `hcl://compliance/en_12464_1` — the EN 12464-1 task table.

**Templates (3) — you fill in the last segment:**

- `hcl://preset/{name}` — a standard illuminant's SPD as JSON, e.g. `hcl://preset/D65`.
- `hcl://action-spectrum/{type}` — a 1-nm action spectrum, e.g. `hcl://action-spectrum/mel`.
- `hcl://compliance/{standard}` — a standard's threshold table, e.g. `hcl://compliance/brown_2022`.

> When in doubt about a number a tool produced, the matching resource explains where it comes
> from: mel-EDI weights → `coefficients`; a compliance threshold → `compliance/{standard}`;
> what a metric means → `glossary`; what *not* to trust → `caveats`.

---

## 5.6 — How to fully utilize it (chaining recipes)

The prompts are convenient, but the real power is composing tools yourself. A few patterns:

**Compare two light sources (no files):**

> Call `presets` for `LED_3000K` and `LED_5000K`; for each, `spd_to_channels` then
> `circadian_metrics` and `spectral_metrics`; show me mel-DER and mel-EDI side by side.

**Daylight at a moment, end to end (with the sample room):**

1. `import_geometry(dry_run=true)` → read the groups.
2. `import_geometry(material_map=…, derive_sensors=true)` → keep `geometry_set`,
   `material_sets`, `observer_sets`, `apertures`.
3. `colored_sky(diffuse_channels, direct_channels, month/day/hour, lat/lon/utc)`.
4. Compose `scene_sets` = the three material+geometry+sky lists; `run_grid(points=observer points, export_csv="grid.csv")`.
5. `compliance(mel_edi=<from the grid>, standard="brown_2022")`.

**Glare + brightness for the same eye view:** run `run_image(fov_weighting=true)` and
`glare_ugr` on the same `scene_sets`+`view`, then read mel-EDI against UGR/DGP together.

**Electric design loop:** `recommend_fixtures` → take its count/spacing → `ies_to_radiance (placement=…)` → `run_grid(electric_lights=…)` → `daylight_savings` → `compliance`.

**Preview a heavy run before paying for it:** add `run: false` to any simulation tool to get the
exact `commands[]` plan first, then re-call with `run: true` (and a tight `period`) when ready.

**Get the most accurate results:**

- Keep `channel_type: 1` (9-channel) for anything circadian/melanopic.
- Set `north_angle_deg` on every import — daylight is wrong without it.
- Use `derive_sensors=true` for scene-accurate eye points instead of hand-written ones.
- Supply **absolute** SPDs only when you need absolute EDI; relative is fine for ratios.
- For annual work, start with a one- or two-hour `period`, confirm it's sane, then widen.

---

## 5.7 — Copy-paste chat scripts (exactly what to type)

New here? Do the **Quick Start** near the top of this guide first — this section is the same idea,
just one card per prompt with the finer detail.

**How to read each prompt card below:**

- **You type** — paste it verbatim. The `/mcp__hcl-mcp__…` name is **Claude Code's** spelling; in
  **Gemini CLI** / **Antigravity** type `/` and pick the same prompt by name, or simply describe it
  in plain English.
- **You'll get** — what comes back.
- **You'll need** — the inputs to have ready (every example points at a sample file in `inputs/`).
- **Behind the scenes** — the tools the prompt runs *for you*, in order (you never call these
  yourself). Quoted from the server source `hcl-mcp/src/hcl_mcp/prompts.py`; to see a prompt's exact
  script, invoke it and read the text it returns.

After you invoke a prompt the assistant follows that script and asks you — conversationally — for
the files and values it needs, so the exact wording of its questions will vary.

### Setup & sanity (do once per session)

```
You type:    /mcp            (Claude Code)   ·   /mcp list   (Gemini CLI)
(look for "hcl-mcp  connected · 50 tools, 13 prompts, 14 resources")

You type:    Call the hcl-mcp validate tool, then radiance_status and daysim_status.
Assistant:   runs all three; you want ok:true and available:true on both status calls.
```

### Calling a single tool (plain English — no slash command)

You don't need exact JSON; describe it and the assistant fills the parameters:

```
You type:   Call presets to fetch D65, then call alpha_opic on that D65 spectrum with
            alpha=5 (melanopic). Show me the EDI and any scale_warning.

You type:   Call spd_to_channels on inputs/spd/L09_neutral.spd with channel_type 1,
            then circadian_metrics on the result. Give me melanopic_lux AND mel_edi,
            and tell me why they differ.   (they are ~9% apart; only mel_edi is the
            quantity the circadian standards are written in)

You type:   Call spectral_metrics on inputs/spd/L09_neutral.spd and tell me the CCT and
            mel-DER.  (try L09_warm.spd / L09_cool.spd too — same fixture, 2700/6500 K)

You type:   Call compliance with mel_edi 280, standard brown_2022, period daytime.
```

### Reading a resource

```
You type:   Read the hcl-mcp resource hcl://index and list what's available.
You type:   Read hcl://reference/coefficients and show the 9-channel melanopic weights.
You type:   Read hcl://compliance/brown_2022 and tell me the daytime threshold.
```

### Prompt 5.1 — explain_concept (learn a concept)

**You type:** `/mcp__hcl-mcp__explain_concept`, then say the **topic** (default `"overview"`; e.g. `"mel-EDI"`, `"coefficients"`).
**You'll get:** a plain-English explainer of that concept.
**You'll need:** nothing.
*Behind the scenes: reads the coefficients/bins + action-spectrum reference resources — no simulation.*

### Prompt 5.2 — spd_to_circadian (a light → a body-clock verdict)

**You type:** `/mcp__hcl-mcp__spd_to_circadian`, then describe the light (**spd_description**, e.g. `"4000 K LED downlight"`).
**You'll get:** the light's CCT, mel-DER, alpha-opic numbers, and a pass/fail against your chosen standard.
**You'll need:** a spectrum — paste `inputs/spd/L09_neutral.spd` (4000 K), or say "use preset D65" — plus a target standard. (Warm/cool: `L09_warm.spd` / `L09_cool.spd`.)
*Behind the scenes: spd_to_channels → alpha_opic → spectral_metrics → compliance.*

### Prompt 5.3 — spectral_sky_from_epw (a physical sky from weather)

**You type:** `/mcp__hcl-mcp__spectral_sky_from_epw`, then say when/where (**location_description**, e.g. `"Athens, June 21 noon"`).
**You'll get:** a physically-derived sky spectrum for that hour, plus its CCT / mel-DER / mel-EDI.
**You'll need:** the EPW `inputs/weather/GRC_Athens.167160_IWEC.epw` + a month/day/hour (6/21/12). Optional: `surface_tilt_deg 90` for a vertical window; try `engine smarts` to compare.
*Behind the scenes: atmosphere_from_epw → spectral_sky_from_epw → alpha_opic + spectral_metrics.*

### Prompt 5.4 — import_obj_room (bring a CAD room in)

**You type:** `/mcp__hcl-mcp__import_obj_room`, then describe the space (**space_description**, e.g. `"4×3 m office, one window"`).
**You'll get:** a ready-to-simulate room (per-channel Radiance scene) with sensors placed for you, then a daylight grid + verdict.
**You'll need:** the OBJ `inputs/geometry/office_room.obj` (furnished, one **south-facing** window) — or `office_room_blinds.obj`, or the `office_room_corner_window*.obj` south-west-corner variants. Its `office_room_material_map.json` ships beside it and is auto-discovered (real reflectances + glass tvis 0.73 + `north_angle_deg 0`). Use units `m`, up-axis `Z`; the geometry is authored in the true-north frame so `north_angle_deg 0` already gives the right compass facing (single = south, corner = south+west) — no need to pass north by hand. (Or skip `import_geometry` and feed `inputs/geometry/radiance/office_room.rad` straight to `run_grid`.)
*Behind the scenes: radiance_status → import_geometry (dry-run, then for real with derive_sensors) → compose scene → run_grid / run_annual → circadian_metrics / compliance.*

### Prompt 5.4a — place_sensors (professional sensor placement)

**You type:** `/mcp__hcl-mcp__place_sensors`.
**You'll get:** an EN 12464-1 work-plane grid, workstation eye sensors (+ glare views), daylight-dimming sensors, and a PNG showing where everything landed — all ready to feed into a run.
**You'll need:** the OBJ `inputs/geometry/office_room.obj` + its `office_room_material_map.json`; units `m`, up-axis `Z`, north `0°`.
*Behind the scenes: import_geometry (dry-run) → workplane_grid → observer_points → photosensors → preview_scene → hand off to run_grid / glare_ugr / run_annual.*

### Prompt 5.4b — visualize_scene (a picture of the placement)

**You type:** `/mcp__hcl-mcp__visualize_scene`.
**You'll get:** PNG plan + 3D views of the room's floor outline with your sensor points drawn on top — a quick "did everything land in the right place?" check.
**You'll need:** the OBJ + its `office_room_material_map.json`; optionally existing `inputs/sensors/*.pts` to preview as-is.
*Behind the scenes: ensure OBJ + material_map → locate/generate the .pts sensor files → preview_scene(render="all") → report the image paths. (This is a diagnostic overlay, not a photometric render — that's run_image.)*

### Prompt 5.5 — hcl_grid_study (daylight at one moment)

**You type:** `/mcp__hcl-mcp__hcl_grid_study`, then describe the space (**space_description**).
**You'll get:** mel-EDI / photopic lux at each sensor for one date-time, plus a pass/fail.
**You'll need:** geometry + materials (from 5.4) or surface SPDs/reflectances; a date/time/place (6/21 12:00, lat 37.9 lon 23.73 utc 2); a target standard.
*Behind the scenes: import_geometry (or write_material) → colored_sky → run_grid → circadian_metrics → compliance.*

### Prompt 5.6 — fisheye_eye_analysis (what the eye sees / glare)

**You type:** `/mcp__hcl-mcp__fisheye_eye_analysis`, then describe the view (**view_description**).
**You'll get:** an eye-level melanopic luminance image (field-of-view weighted) + a verdict.
**You'll need:** a scene (from 5.4/5.5); optionally a `glare_views` string from the import to use as the `view`. For UGR/DGP numbers too, also call `glare_ugr` on the same scene+view.
*Behind the scenes: run_image(fov_weighting=True) → compliance.*

### Prompt 5.7 — electric_lighting_design (electric + daylight + energy)

**You type:** `/mcp__hcl-mcp__electric_lighting_design`, then describe the space (**space_description**).
**You'll get:** the combined daylight-plus-electric grid, glare, and lighting-energy savings, graded against EN 12464-1.
**You'll need:** the IES `inputs/luminaires/L09_neutral.ies` (Glamox C95 600×600, 4000 K) + a placement (e.g. a 2×2 ceiling grid at 2.6 m); geometry + materials + sky; targets 500 lux + 250 mel-EDI. Swap `L09_warm.ies` / `L09_cool.ies` (same fixture, 2700/6500 K) to watch mel-EDI shift.
*Behind the scenes: ies_analyze → ies_to_radiance → run_grid(+electric_lights) → daylight_savings → compliance(en_12464_1).*

### Prompt 5.8 — annual_circadian_dose (a whole year of daylight — keep the window tiny!)

**You type:** `/mcp__hcl-mcp__annual_circadian_dose`, then describe the space (**space_description**).
**You'll get:** the year's melanopic dose per point + hours-above-threshold.
**You'll need:** the WEA `inputs/weather/GRC_Athens.167160_IWEC.wea` (from the EPW); geometry; observer points; a **tight** period like `[[6,21,8],[6,21,18]]`; `dosimetry_threshold 250`. For the source breakdown, add `apertures=[{name:"Room_Window", glazing_modifier:"Rad_Glazing_T073"}]` (the glass group name from the import) and `validate true`.
*Behind the scenes: weather → run_annual → recombine → hours-above-threshold.*

### Prompt 5.8a — annual_daylight_study (climate-based daylight: DA/UDI/DF/sDA/ASE)

**You type:** `/mcp__hcl-mcp__annual_daylight_study`, then describe the space (**space_description**).
**You'll get:** the standard green-building daylight metrics — DA / cDA / UDI per point, spatial sDA / ASE, Daylight Factor, and annual energy savings — to grade against LEED v4 / EN 17037.
**You'll need:** the WEA `inputs/weather/GRC_Athens.167160_IWEC.wea`; geometry + materials; a work-plane grid (auto-derived, or saved with `sensors`). This is the **visual/photopic twin** of 5.8 (which is melanopic); it runs the full 8760 h, so it's slow.
*Behind the scenes: sensors(create work-plane) → annual_daylight → daylight_factor → daylight_savings(mode="annual").*

### Prompt 5.9 — annual_alertness (year-long alertness, nvRD — needs Daysim)

**You type:** `/mcp__hcl-mcp__annual_alertness`, then describe the space (**space_description**).
**You'll get:** a year-long relative-alertness (R_D) time series, computed two ways with their divergence. **Read it relatively** (compare scenarios), never as an absolute number.
**You'll need:** the EPW `inputs/weather/GRC_Athens.167160_IWEC.epw`; one eye point + gaze direction (e.g. point `[2,1.5,1.2]`, view `[0,-1,0]`); keep `timestep_min` at the default 6. (Long-running; asks to confirm.)
*Behind the scenes: daysim_status [→ build_daysim] → generate_subhourly_wea → annual_nvrd(reconstruction="both").*

### Prompt 5.10 — hcl_studio (the full guided study — the front door)

**You type:** `/mcp__hcl-mcp__hcl_studio` with a **space_description** and **daylight_aware** (true/false).
**You'll get:** a complete start-to-finish study over 8 phases, ending in a `report.md` / `report.html` with a target-vs-achieved verdict. Progress is saved after every phase — resume by re-invoking and saying "resume study &lt;slug&gt;".
**You'll need:** a study slug (e.g. `athens_office`); room dims/reflectances + a mel-EDI target; optionally an OBJ + IES + EPW (paths under `inputs/`).
*Behind the scenes: 0 validate + status → 1 goal → 2 import_geometry → 3 daylight baseline → 4 recommend_fixtures → 5 ies_analyze + ies_to_radiance → 6 run_grid (+ annual/nvrd) → 7 daylight_savings → 8 build_report (save_brief after each; load_brief to resume).*


### A full manual run, no prompts (paste these in order)

If you'd rather drive the tools yourself instead of using a prompt:

```
1)  Import the room and keep the outputs:
You type:   Call import_geometry on inputs/geometry/office_room.obj with dry_run true and
            show me the groups.  (or office_room_blinds.obj for the room with blinds)
You type:   Now call import_geometry again (the pinned office_room_material_map.json beside the
            OBJ is auto-discovered — or pass material_map yourself). It sets units m, up_axis Z and
            north_angle_deg 0 (the room is authored in the true-north frame → window faces south) for you
            — don't override north unless you mean to rotate the whole building.
            Add derive_sensors true, channel_type 1. Keep geometry_set, material_sets, observer
            points and apertures.

2)  Build the sky for the moment:
You type:   Call colored_sky for June 21, hour 12, lat 37.9 lon 23.73 utc 2, irrad_mode W,
            direct 600, diffuse 150, channel_type 1. Use neutral diffuse/direct channels.

3)  Run the grid and judge it:
You type:   Compose scene_sets from the material_sets + geometry_set + the sky, then call
            run_grid with the observer points, channel_type 1, export_csv grid.csv.
You type:   Take the melanopic-EDI from that grid and call compliance against brown_2022,
            period daytime.
```

# PART 6 — Understanding the science & the numbers

You can run everything above without this part. Read it when you want to know *what a number
means*, *how it's computed*, and — most importantly — *how far to trust it*. Everything here is
distilled from the project's own reference docs (links at the end); they hold the full equations
and citations.

## 6.1 The big picture: two halves of the engine

The toolbox is two coupled "domains" (from
[hcl-methodology.md](../docs/hcl-methodology.md)):

- **Domain A — the spectral / circadian chain (point-wise, instant, no files).** One spectrum
  in → colour and circadian metrics out: `spd_to_channels` → `circadian_metrics` /
  `alpha_opic` → `spectral_metrics` → `compliance`. This is the pure-Python core; it always
  runs.
- **Domain B — the annual spatial transport (geometry + weather, heavy, needs Radiance).**
  Room + materials + sky → per-sensor, per-timestep light via Radiance ray-tracing → dose,
  glare, and (via a bridge back into Domain A) alertness.

The **bridge** between them is *reconstruction*: Domain B produces binned channels, which are
expanded back into a full spectrum so the same Domain A circadian math applies per timestep.

## 6.2 What each metric means (and how it's computed)

| Metric                  | Plain meaning                                                                      | How it's computed (short)                                                                      |
| ----------------------- | ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| **Photopic lux**  | ordinary "brightness" your visual system sees                                      | `179 × Σ(photopic_weightᵢ · channelᵢ)`, or the exact `683·Σ E(λ)V(λ)` from an SPD |
| **Melanopic lux** | light as your**body clock** (ipRGC) sees it                                  | same form, with the melanopic weights                                                          |
| **Neuropic lux**  | the OPN5 (9-channel only) response                                                 | same form, OPN5 weights, ~90 % in the deep blue                                                |
| **mel-EDI**       | melanopic Equivalent Daylight Illuminance — the headline circadian number, in lux | α-opic melanopic irradiance ÷ the D65 reference, ×1000 (CIE S 026)                          |
| **mel-DER**       | melanopic "efficiency per lux" of a source, D65 ≡ 1.0                             | melanopic ELR of the source ÷ that of D65 (scale-free)                                        |
| **EML**           | equivalent melanopic lux (older WELL currency)                                     | `EML = 1.103 × mel-EDI`                                                                     |
| **CCT / Duv**     | colour temperature + distance from the Planckian locus                             | SPD → XYZ → CIE 1960 uv → Ohno 2013 inversion                                               |
| **R_D (nvRD)**    | relative alerting response over time                                               | Amundadottir model: ipRGC irradiance → 3-filter temporal cascade → adaptive sigmoid          |

**Anchor values to sanity-check against** (from
[hcl-methodology.md](../docs/hcl-methodology.md)): D65 → CCT 6503 K, mel-DER **1.000**;
CIE A (incandescent) → 2856 K, mel-DER **0.496**; D50 → mel-DER 0.847; a 5000 K LED → ~0.818.
Warm light has a *lower* mel-DER than cool light — as expected. The luminous-efficacy constant
throughout is **179 lm/W** (the Radiance convention).

**Two accuracy facts worth knowing:**

- **Use 9-channel (`channel_type: 1`).** The 3-channel path is supported but flagged
  *approximate* (a deliberate bin-alignment fix makes it differ from the legacy tool); the
  9-channel path matches the reference bit-for-bit.
- **For *absolute* mel-EDI, feed an SPD, not channels.** The channel→spectrum path carries an
  undocumented `1/107` lineage constant that cancels in *ratios* (mel-DER, relative EDI) but not
  in *absolute* irradiance or the non-linear nvRD sigmoid. So absolute mel-EDI and R_D from the
  channel path are unvalidated — `alpha_opic(spd=…)` is the gold-standard absolute path.

## 6.3 Annual daylight: the 2-phase method

`run_annual` uses the **2-phase Daylight-Coefficient + Direct Sun (DDS)** method (Subramaniam
2017). It transports two things separately and adds them:

- **Sky-diffuse** — the sky vault split into **145 patches** (Reinhart MF:1), **coloured**.
- **Sun-direct** — **~5165 solar-disc** positions (MF:6), **neutral** (Radiance can't colour the
  direct beam; a known, documented limitation).

The per-sensor result is a year (or your `period`) of melanopic-EDI; dosimetry then counts hours
above your threshold (default 250 mel-EDI lux). The meaningful sensor for circadian work is
**vertical, at the eye, facing the glazing** — orient your points that way. Full math:
[hcl-methodology.md §12](../docs/hcl-methodology.md).

**Two tracks over the same transport.** The annual illuminance the DDS pass produces feeds two
distinct metric families:

- **Melanopic / circadian** (`run_annual`) — the *body-clock* dose at the
  vertical eye, in mel-EDI, described above.
- **Photopic / visual** (`annual_daylight`, `daylight_factor`) — the standard *climate-based
  daylight-performance* metrics on the horizontal work-plane, used in green-building compliance:

  - **DA / cDA** — Daylight Autonomy: the fraction of occupied hours a point clears `da_threshold`
    (300 lx); cDA gives partial credit `min(1, E/threshold)`.
  - **UDI** — Useful Daylight Illuminance: occupied hours binned `<100 / 100–300 / 300–3000 / >3000`
    lx — i.e. *too dark / partly useful / fully useful / too bright* (the last is a glare risk).
  - **sDA** — spatial DA: the fraction of points with DA ≥ 50 % → the headline **sDA300/50%**.
  - **ASE** — Annual Sunlight Exposure: the fraction of points seeing **direct** sun ≥ 1000 lx for
    more than 250 occupied hours; a glare/overheating proxy. ASE is computed from direct sunbeams
    only — bounced light is switched off (the `-ab 0` Radiance flag) — so it is a *separate* run
    from DA/UDI (which use the full bounced daylight); don't mix the two numbers.
  - **DF** — Daylight Factor: `E_indoor / E_outdoor × 100` under a CIE Standard Overcast Sky
    (`daylight_factor`); a sun-free, single-run code-based companion to sDA.

  Grade `sDA300/50%` + `ASE1000,250h` against **LEED v4 EQ "Daylight"** / **EN 17037**. The
  `annual_daylight_study` prompt orchestrates the whole photopic chain over a persistent
  `sensor_set`. Metric math: `hcl-mcp/docs/annual-daylight-metrics-as-built.md`.

## 6.4 Melanopic source attribution — moved out

> Melanopic source attribution moved out; the engine and its method doc
> (`melanopic-attribution-methodology.md`) now live in a companion study, a separate
> repository outside this one.
> The `annual_attribution` tool is no longer part of this server, so there is nothing to validate here.

## 6.5 Physical spectral sky — which engine, when

`spectral_sky_from_epw` reconstructs a real 1-nm sky spectrum from a weather hour:
EPW → atmosphere (AOD/PWV/ozone) + solar geometry → a **clear-sky engine** → the **SEDES1 cloud
bridge** (rescales energy to the EPW's measured DNI/DHI, always; reshapes the diffuse by cloudiness)
→ 1-nm record. The **one rule** (from
[spectral-sky-methodology.md](../docs/spectral-sky-methodology.md) and the operating guide):
**bluer ≠ better.**

| You need…                                                      | Use                               | How                                          |
| --------------------------------------------------------------- | --------------------------------- | -------------------------------------------- |
| Fast, portable spectrum for any hour —**the default**    | **SPECTRL2** (pure Python)  | `engine: "spectrl2"`                       |
| Reference direct-beam / max spectral resolution                 | **SMARTS**                  | `engine: "smarts"` (needs `$SMARTSPATH`) |
| Façade- / eye-level**colour & melanopic** (the HCL case) | **gensdaymtx**              | `spectral_sky_native` (Radiance 6.x)       |
| Horizontal roof / energy / photopic number                      | any — they agree by construction | default is fine                              |

Why it matters: for a **horizontal** sensor all three engines agree (they're anchored to the
EPW's diffuse-horizontal). The moment the receiver is a **vertical façade or an eye**, angular
structure is first-order — only `gensdaymtx` (or the optional anisotropic wrapper) has it. SMARTS
is the *bluest* engine, which makes it the **largest melanopic error** off-horizontal, not an
asset. Validation status: SPECTRL2's direct beam matches the Fortran reference to <0.05 %; SMARTS
agrees with SPECTRL2 to ~2 % direct / ~7 % diffuse (r≈0.99); `gensdaymtx` confirmed at NCOMP=20
(Pearson 0.987) — these are validation runs, not certified baselines. The `physical_sky=True` flip
into the alertness path is opt-in and **not yet live-validated**.

**Opt-in atmosphere refinements (defaults reproduce prior output byte-for-bit).** Four knobs let you
push the atmosphere beyond the defaults, all on `atmosphere_from_epw`/`spectral_sky_from_epw`/`spectral_epw`:
`ozone_mode="climatology"` (van Heuklon 1979 ozone from the EPW LOCATION lat/lon + date — hemisphere-specific,
NH spring-max; default constant 0.30), `aerosol_g` (aerosol asymmetry, default 0.65), `aod_anchor_nm`
(Ångström-convert a declared-wavelength/satellite AOD to τ₅₀₀), and — SMARTS only — `smarts_aerosol="user"`
(settable Ångström α + `g` via an `AEROS='USER'` card). Reach for these when you have measured/satellite
atmosphere data; the defaults leave every prior result unchanged. See spectral-sky-methodology.md §6 and
spectral-sky-as-built.md D-2/D-3/D-7/D-20.

## 6.6 Fixture sizing — what `recommend_fixtures` actually does

It reconciles **two** requirements from first principles (no product catalog):

- **Visual (lumen method):** `Φ = Ēm · A / (UF · MF)` — daylight is *not* subtracted (the
  installation must meet the task level on its own).
- **Circadian (mel-DER solve):** required mel-DER = (target mel-EDI − daylight mel-EDI) /
  vertical eye illuminance, where vertical ≈ `Ēm × 0.4` (the V/H ratio — the dominant
  uncertainty).

The bigger of the two flux requirements wins; a spacing-to-height grid sets the layout. The
circadian solve produces three bands: reachable (≤ ~0.82 mel-DER, an example CCT is named),
reachable-but-beyond-the-palette (0.82–1.2 → go cooler, verify on the real SPD), or impossible
(> 1.2 → no spectrum can do it; it flags `binding_constraint: "circadian"` and advises
supplementary fixtures). **Treat the spec as a starting point, not the verdict** — it's
illustrative; phases 5–6 (`ies_analyze` on the real IES, then `run_grid` measuring real mel-EDI)
are authoritative. Detail: [operating-guide.md §G.1](../docs/operating-guide.md).

## 6.7 How far to trust each result (the honesty ledger)

The project is unusually explicit about its own limits. The short version:

| Area                                               | Trust level                                                                                                               |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Spectral core (channels, α-opic, CCT, compliance) | **Solid** — literature-grounded, self-tested, golden-anchored. Use 9-channel.                                      |
| Absolute mel-EDI / R_D from**channels**      | **Relative only** — use the **SPD** path for absolute values.                                                |
| `compliance` thresholds                          | Faithful to the standards, but flagged where a standard is informative/external; "verify against the live standard text." |
| Electric lighting / glare pipeline                 | Math reproduces golden values; some live paths are emit/mock-tested — verify live before trusting.                       |
| `recommend_fixtures`                             | **Illustrative** first-principles sizing — a plausibility check, not ground truth.                                 |
| nvRD`R_D`                                        | **Relative**, validated on night-time studies; daytime envelope ~±20 %. Compare scenarios, never read as absolute. |
| Physical-sky`physical_sky=True`                  | Correct-by-construction + unit-tested;**not** live-validated.                                                       |
| SEDES1 cloud reshape                               | Only the energy-rescale to EPW DNI/DHI is exact; the spectral*shape* carries figure-digitization uncertainty.           |

When a result is relative or approximate, the tools **say so in-band** — read keys like
`scale_warning`, `relative_RD_note`, `validation.available`, `divergence`, and the `caveats`
lists. They aren't noise; they're the tool telling you where the floor is.

## 6.8 Where to read the full story

- [operating-guide.md](../docs/operating-guide.md) — every workflow A–I, the run/emit
  contract, the engine decision guide.
- [hcl-methodology.md](../docs/hcl-methodology.md) — all the core equations (H-n): α-opic,
  nvRD, 2-phase transport, controls, compliance.
- [spectral-sky-methodology.md](../docs/spectral-sky-methodology.md) — the EPW→spectral-sky
  physics (M-n): SPECTRL2, SMARTS, SEDES1.
- `melanopic-attribution-methodology.md` — the leaf-grid decomposition (A-n); this doc and the
  engine moved to a companion study, a separate repository outside this one.
- [technical-reference.md](../docs/technical-reference.md) — a module-by-module code map.
- In-chat: the `reference` tool (`topic: "overview"`) and the `hcl://reference/*` resources
  (especially `glossary` and `caveats`).

---

# PART 7 — When something breaks (troubleshooting)

> Throughout this table, **"restart your client"** means restart whichever AI assistant you
> connected (Claude Code / Gemini CLI / Antigravity) — they all read their MCP config only at
> startup. "Config file" = `.mcp.json` for Claude Code, or the `settings.json` / `mcp_config.json`
> for Gemini CLI / Antigravity ([Part 1B](#part-1b--connect-to-gemini-cli-or-antigravity)).

| What you see                                              | What it means and how to fix it                                                                                                                                                                                                                                                                                                                                                              |
| --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `hcl-mcp` tools are missing                             | The config file didn't load. Confirm your client is launched in the project folder`/path/to/hcl_mcp` (Windows: `C:\Users\<you>\Desktop\hcl_mcp`) — or that the config is in the right global location — then **fully restart the client** and approve the server when asked. Make sure `uv sync` (Step 1.1) finished.                                                          |
| `ModuleNotFoundError: hcl_core`                         | A path setting (`PYTHONPATH`) wasn't applied. It's already in the config — just **restart your client**. (If launching by hand, prepend `PYTHONPATH=…/hcl-mcp/src`.)                                                                                                                                                                                                             |
| `UnmappedGroupsError` when importing a room             | Your`material_map.json` is missing a group. Add **every** name from the dry-run `groups` list as a key.                                                                                                                                                                                                                                                                            |
| A tool returns`"ran": false` with a `commands[]` list | **Normal** if you haven't installed that engine — the tool returns the exact command *plan* instead of running, which counts as a pass. If you *did* install it but still get this, the engine path in the config didn't load: check the `env` value and **restart your client**. Install engines: [Appendix A](#a--installing-the-engines-optional--for-live-simulation). |
| `daysim_status.available = false` after install         | Config not picked up —**restart your client**; confirm `ds_shortterm` (+ `epw2wea`) exist in the folder your `HCL_DAYSIM_BIN` points at (`.exe` on Windows). Not installed yet? See [Appendix A](#a--installing-the-engines-optional--for-live-simulation).                                                                                                                    |
| `run_annual` says it skipped because of `reinsrc.cal` | That helper file isn't in the Radiance library. Copy it (see appendix §A); no restart needed.                                                                                                                                                                                                                                                                                               |
| `ds_shortterm … timestep_min … rejected`              | The sub-hourly step must be one of`{1,2,3,4,5,6,10,12,15,20,30}` (60 is rejected). For the alertness path keep the **default 6** — the nvRD model needs ≤ 0.3 h steps, so 20/30 raise too.                                                                                                                                                                                         |
| `engine="smarts"` raises an error                       | The SMARTS path isn't loaded —**restart your client**, or just use the default `spectrl2` engine.                                                                                                                                                                                                                                                                                   |
| An annual / native-sky run takes forever                  | A full year is 8760 hours. Use a**tight `period`/`hours`** (a single hour or two), or set a `timeout`.                                                                                                                                                                                                                                                                           |
| `scale_warning` on `alpha_opic`                       | Your spectrum looks relative (peak ≤ 1.5). Fine for color/ratio metrics; supply absolute W·m⁻²·nm⁻¹ only if you need absolute EDI.                                                                                                                                                                                                                                                    |

---

# A — Installing the engines (optional — for live simulation)

**The engines are optional.** The pure-Python spectral core (Parts 5.2–5.4 group A) always works.
The *simulation* tools (daylight grids, images, glare, annual, native spectral sky, alertness) call
external physics engines — **if an engine is installed they run for real; if not, they emit the
exact command plan instead, which is a valid result, not an error** (capability gating, §5.2.3). So
install only the engines whose workflows you actually need. The toolbox finds each engine through a
path in your client config's `env` block (the `HCL_*`/`RAYPATH`/`SMARTSPATH` variables) — so after
installing one, set its variable and **restart your AI client** (except `reinsrc.cal`, read at run
time).

> **→ Step-by-step, agent-runnable version of this appendix (get source → build → set env → verify):**
> [`../docs/engines-install.md`](../docs/engines-install.md).

### Where to get each engine

| Engine                                               | Powers                                                                                         | Download / source                                                                                                                                                                                                                                       | License                                |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| **Radiance** (≥ 5.3; 6.x for native spectral) | grid, image, glare, annual,`ies2rad`, `epw2wea`, `gensdaymtx`                            | **[github.com/LBNL-ETA/Radiance/releases/latest](https://github.com/LBNL-ETA/Radiance/releases/latest)** — prebuilt installers for **Windows, macOS (x86-64 & arm64), Linux**. Info: [radiance-online.org](https://www.radiance-online.org/) | Open source (free)                     |
| **Daysim**                                     | `generate_subhourly_wea`, live `annual_nvrd` transport                                     | **[github.com/MITSustainableDesignLab/Daysim](https://github.com/MITSustainableDesignLab/Daysim)** — source to build (Win/macOS/Linux via CMake)                                                                                                  | Source-available (NRC/Fraunhofer EULA) |
| **SMARTS 2.9.5**                               | `engine="smarts"` reference sky spectrum (optional; `spectrl2` is the pure-Python default) | **[nrel.gov/grid/solar-resource/smarts.html](https://www.nrel.gov/grid/solar-resource/smarts.html)** (free, license-gated; Windows/macOS/Linux builds)                                                                                             | Civilian research/education            |
| `uv` (Python runner — needed by Step 1.1)         | launching the server                                                                           | **[github.com/astral-sh/uv](https://github.com/astral-sh/uv)** (`curl -LsSf https://astral.sh/uv/install.sh \| sh`; Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 \| iex"`)                                                      | Open source                            |

The exact build/copy commands for each platform follow. Substitute **your** install locations for the
example paths below (`/usr/local/…`, `C:\…`) — they're just conventional choices, not requirements;
what matters is that the matching `env` variable points at where you actually put the binaries.

> **Path-separator reminder (Windows):** in list variables like `RAYPATH`, separate entries with
> a semicolon `;` on Windows (e.g. `RAYPATH=.;C:\Radiance\lib`) but a colon `:` on macOS / Linux
> (`RAYPATH=.:/usr/local/radiance/lib`). All engine executables get a `.exe` suffix on Windows.

### Radiance — the main light engine

Get a prebuilt installer for your OS from **[github.com/LBNL-ETA/Radiance/releases/latest](https://github.com/LBNL-ETA/Radiance/releases/latest)**
(Windows `.exe`, macOS x86-64/arm64, Linux). Then:

- **macOS / Linux:** install into a prefix like `/usr/local/radiance` (or anywhere). Set
  `HCL_RADIANCE_BIN=<prefix>/bin` and `RAYPATH=.:<prefix>/lib`.
- **Windows:** run the installer (or unzip the release) to e.g. `C:\Radiance`. Set
  `HCL_RADIANCE_BIN=C:\Radiance\bin` and `RAYPATH=.;C:\Radiance\lib`.

### `reinsrc.cal` — needed for the year-long solar-disc step

Some Radiance builds omit this Reinhart helper file; without it the annual tools degrade to printing
a plan (with an honest reason). It ships in the Radiance and Daysim source trees (under
`src/cal/cal/reinsrc.cal`); copy it into your Radiance `lib`:

- **macOS / Linux:**
  ```bash
  sudo cp <radiance-or-daysim-src>/src/cal/cal/reinsrc.cal "$HCL_RADIANCE_BIN/../lib/"
  ```
- **Windows** (PowerShell; "Run as Administrator" if `lib` sits under `C:\`):
  ```powershell
  Copy-Item <radiance-or-daysim-src>\src\cal\cal\reinsrc.cal C:\Radiance\lib\
  ```

### Daysim — annual daylight + alertness

Daysim isn't bundled (source-available EULA); **clone and build it** from
**[github.com/MITSustainableDesignLab/Daysim](https://github.com/MITSustainableDesignLab/Daysim)**
(`git clone https://github.com/MITSustainableDesignLab/Daysim.git`). You only need the
`ds_shortterm` + `epw2wea` targets. (The server's `build_daysim` tool also automates this — call it
with `run:true`.)

- **macOS / Linux:**

  ```bash
  # cmake: macOS `brew install cmake`; Linux `apt install cmake` / `dnf install cmake`
  cmake -S Daysim -B build -DBUILD_HEADLESS=ON -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_POLICY_VERSION_MINIMUM=3.5     # Apple Silicon: add -DCMAKE_OSX_ARCHITECTURES=arm64
  cmake --build build --target ds_shortterm epw2wea
  sudo mkdir -p /usr/local/daysim/bin
  sudo cp build/bin/{ds_shortterm,epw2wea} /usr/local/daysim/bin/
  ```

  Then set `HCL_DAYSIM_BIN=/usr/local/daysim/bin` (or wherever you put them).
- **Windows** — install CMake (`winget install Kitware.CMake`) and the Visual Studio Build Tools, then:

  ```powershell
  cmake -S Daysim -B build -DBUILD_HEADLESS=ON -DCMAKE_BUILD_TYPE=Release `
        -DCMAKE_POLICY_VERSION_MINIMUM=3.5
  cmake --build build --config Release --target ds_shortterm epw2wea
  New-Item -ItemType Directory -Force C:\Daysim\bin
  Copy-Item build\bin\Release\ds_shortterm.exe,build\bin\Release\epw2wea.exe C:\Daysim\bin\
  ```

  Then set `HCL_DAYSIM_BIN=C:\Daysim\bin`.

### SMARTS 2.9.5 — optional reference sky spectrum

Download from NREL (free, license-gated): **[nrel.gov/grid/solar-resource/smarts.html](https://www.nrel.gov/grid/solar-resource/smarts.html)**.
Only needed for `engine="smarts"`; the pure-Python `spectrl2` engine is the default and needs nothing.

- **macOS / Linux:** compile the batch executable (e.g. to `~/smarts/smarts295bat`; arm64 on Apple
  Silicon); point `SMARTSPATH` at the binary **file** (not its directory), and keep its data folders
  (`Gases/`, `Albedo/`, …) beside it. Build steps: [`../docs/smarts-build.md`](../docs/smarts-build.md).
- **Windows:** the distribution ships a ready-to-run console executable (`smarts295bat.exe`) — unzip
  it (e.g. to `C:\smarts`), set `SMARTSPATH=C:\smarts\smarts295bat.exe` (the executable **file**, not the
  folder — a directory value is rejected), and keep the data folders alongside.

### Registering the server from the command line (alternative to editing the config by hand)

Prefer the command line over editing the config file? Register the server this way instead (still
requires a restart). Substitute *your* project root on Windows.

This `claude mcp add` form is **Claude Code's** CLI. Newer **Gemini CLI** builds have the equivalent
`gemini mcp add hcl-mcp --env … -- uv run …` (run `gemini mcp --help` to confirm the flags for your
version); **Antigravity** has no add-CLI — edit its `mcp_config.json` directly
([Part 1B](#part-1b--connect-to-gemini-cli-or-antigravity)). The `--env` values and the
`uv run …` command are identical for all of them.

- **macOS / Linux (Claude Code):**
  ```bash
  claude mcp add hcl-mcp \
    --env PYTHONPATH=/path/to/hcl_mcp/hcl-mcp/src \
    --env HCL_RADIANCE_BIN=/usr/local/radiance/bin \
    --env HCL_WORK_ROOT=/path/to/hcl_mcp/hcl_validation/results/work \
    --env RAYPATH=.:/usr/local/radiance/lib \
    --env SMARTSPATH=/path/to/smarts/smarts295bat \
    --env HCL_DAYSIM_BIN=/usr/local/daysim/bin \
    -- uv run --directory /path/to/hcl_mcp/hcl-mcp hcl-mcp
  ```
- **Windows** (PowerShell — backslash paths, and quote `RAYPATH` so PowerShell doesn't split on
  the `;`):
  ```powershell
  claude mcp add hcl-mcp `
    --env PYTHONPATH=C:\Users\<you>\Desktop\hcl_mcp\hcl-mcp\src `
    --env HCL_RADIANCE_BIN=C:\Radiance\bin `
    --env HCL_WORK_ROOT=C:\Users\<you>\Desktop\hcl_mcp\hcl_validation\results\work `
    --env "RAYPATH=.;C:\Radiance\lib" `
    --env SMARTSPATH=C:\smarts `
    --env HCL_DAYSIM_BIN=C:\Daysim\bin `
    -- uv run --directory C:\Users\<you>\Desktop\hcl_mcp\hcl-mcp hcl-mcp
  ```

---

# B — Complete parameter reference (every tool, every option)

Part 5.4 listed the inputs you set *most often*. This appendix is the **full** signature of every
tool: each parameter, its **default** (in `code`), and what each choice does — so you can drive any
tool to its limit, not just its happy path. Same plain-language style; just exhaustive.

**How to read it.** A parameter shown as `name = default` is optional (the server fills the
default if you don't); a parameter with **no** `=` is required. Every simulation tool also takes the
two universal knobs in the box just below, so they're not repeated in each table.

### B.0 — Knobs that appear on (almost) every simulation tool

| Param            | Default          | What it does                                                                                                                                                                                             |
| ---------------- | ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `run`          | `true`         | `true` = execute the engine. `false` = **emit** the exact `commands[]` plan without running (capability gating, §5.2.3). Use `false` to preview a heavy run, or when an engine is absent. |
| `work_dir`     | server work root | Folder where the tool writes its outputs (`.rad`, `.hdr`, `.csv`, reports). Relative `export_csv`/`subset_out`/etc. paths resolve inside it.                                                   |
| `rad_params`   | `null`         | Extra Radiance`rtrace`/`rpict` quality flags passed straight through, e.g. `"-ab 4 -ad 2048 -aa 0.1"` (more bounces/samples = slower, more accurate). Omit for the built-in defaults.              |
| `channel_type` | `1`            | `1` = 9-channel (accurate melanopic/circadian — **keep this**). `0` = 3-channel (RGB; `glare_ugr` defaults to it, fine for visual-only). Must match across a chain.                         |

### B.1 — The choice-parameter cheat sheet (every enum in one place)

Every parameter that takes a fixed set of values, so you never have to guess a spelling:

| Parameter (tool)                                               | Allowed values                                                                                                                                                                                                       |
| -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `channel_type` (all)                                         | `0` (3-ch RGB) · `1` (9-ch — default)                                                                                                                                                                          |
| `alpha` (`alpha_opic`)                                     | `1`=S-cone · `2`=M-cone · `3`=L-cone · `4`=rhodopic · `5`=melanopic · omit=all five                                                                                                                   |
| `standard` (`compliance`)                                  | `brown_2022` (default) · `well_v2_l03` · `iso_cie_8995_1_2025` · `en_17037` · `en_12464_1` · `ul_24480`                                                                                             |
| `period` (`compliance`)                                    | `daytime` (≥250) · `evening` (≤10) · `sleep` (≤1) · `night` (≤10)                                                                                                                                     |
| `metric` (`spectral_metrics`)                              | `all` (default) · `cct_duv` · `mel_der` · `mel_photopic_ratio` · `eml_edi`                                                                                                                             |
| `eml_edi_direction` (`spectral_metrics`)                   | `medi_to_eml` (default) · `eml_to_medi`                                                                                                                                                                         |
| `material_type` (`write_material`)                         | `0`=glass · `1`=plastic                                                                                                                                                                                         |
| `type` (in a `material_map` spec)                          | `plastic` · `glass` · `ground` · `context` · `luminaire` · `floor`                                                                                                                                  |
| `mode` (`colored_sky`)                                     | `spectra` (per-channel, runs gendaylit — default) · `luminance` (Radiance `-C`, 3-ch only, emit)                                                                                                             |
| `irrad_mode` (`colored_sky`)                               | `W` (direct+diffuse — default) · `E` (global)                                                                                                                                                                  |
| `count` (`colored_luminaire`)                              | `0`=blue · `1`=green · `2`=red third of the 9 channels                                                                                                                                                       |
| `units` (`import_geometry`)                                | `mm` · `cm` · `m` · `ft`                                                                                                                                                                                  |
| `up_axis` (`import_geometry`)                              | `Y` · `Z`                                                                                                                                                                                                       |
| `distribution` (`recommend_fixtures`)                      | `direct` (default) · `direct_indirect` · `indirect`                                                                                                                                                          |
| `control_type` (`lighting_controls`, `daylight_savings`) | `ContinuousOff` (default) · `Continuous` · `Stepped`                                                                                                                                                         |
| `mode` (`daylight_savings`)                                | `point_in_time` (default, uses `run_grid`) · `annual` (uses `run_annual`, single point)                                                                                                                     |
| `units` (`ies_to_radiance`)                                | `2` = meters (default) · `1` = feet (ies2rad `-d`)                                                                                                                                                            |
| `method` (`reconstruct_spectrum`)                          | `reference` (default) · `faithful` (legacy flat)                                                                                                                                                                |
| `sun_spectral` (`reconstruct_spectrum`, `annual_nvrd`)   | `colored` (air-mass solar SPD — default) · `neutral` (flat)                                                                                                                                                    |
| `reconstruction` (`annual_nvrd`)                           | `both` (default) · `faithful` · `enhanced`                                                                                                                                                                   |
| `sky_reconstruction` (`annual_nvrd`)                       | `reference` (static shape — default) · `dseries` (per-timestep CIE D-series)                                                                                                                                   |
| `engine` (spectral-sky tools)                                | `spectrl2` (pure Python — default) · `smarts` (needs `$SMARTSPATH`)                                                                                                                                          |
| `mode` (`spectral_sky_native`)                             | `all` (default) · `sun` (`-d`) · `sky` (`-s`)                                                                                                                                                            |
| `forms` (`spectral_epw`)                                   | any subset of`spd_set` · `band_matrix` · `spectral_wea` · `sidecar` (default = all)                                                                                                                       |
| `topic` (`reference` / `explain_concept`)                | `overview` (default) · `coefficients` · `bins` · `caveats`                                                                                                                                                |
| `type` (`hcl://action-spectrum/{type}`)                    | `S` · `M` · `L` · `rhod` · `mel` · `V` · `D65`                                                                                                                                                   |
| `timestep_min` (Daysim tools)                                | one of`1,2,3,4,5,6,10,12,15,20,30` — **`6` is the safe default**; nvRD needs ≤15; `60` is rejected                                                                                                     |
| EN 12464-1 task (used with`standard="en_12464_1"`)           | `office_writing_reading` · `office_technical_drawing` · `office_conference` · `office_filing_copying` · `office_reception` · `classroom` · `classroom_evening_adult` · `corridor_circulation` |

### B.2 — Spectral core (group A)

**`validate()`** — no parameters.

**`presets(name = null)`** — `name` omitted ⇒ list all; give a name (`D65`, `D50`, `A`, `FL1`–`FL12`,
`LED_3000K/4000K/5000K/BLUEPUMP/VIOLETPUMP`) to fetch that SPD + metadata. (LED models are illustrative.)

**`spd_to_channels(spd, channel_type = 1)`**

| Param            | Default | What it does                                                                                                       |
| ---------------- | ------- | ------------------------------------------------------------------------------------------------------------------ |
| `spd`          | —      | A`.spd` **file path**, 2-column text (`wl value`), **or** a list of `[wavelength, value]` pairs. |
| `channel_type` | `1`   | `1`→9 channels `[b1..r3]`; `0`→3 channels `[r,g,b]`.                                                     |

**`alpha_opic(channels = null, spd = null, channel_type = 1, alpha = null)`**

| Param                       | Default  | What it does                                                                                        |
| --------------------------- | -------- | --------------------------------------------------------------------------------------------------- |
| `channels` *or* `spd` | —       | Supply**one**. `spd=` is the gold-standard absolute path; `channels=` is the binned path. |
| `channel_type`            | `1`    | Bin layout of`channels` (ignored when you pass `spd`).                                          |
| `alpha`                   | `null` | `1`=S, `2`=M, `3`=L, `4`=rhodopic, `5`=melanopic; omit = all five.                        |

> On the `spd=` path a `scale_warning` appears when the SPD looks **relative** (peak ≤ 1.5) — the
> EDI is then a shape indicator, not lux. Feed absolute W·m⁻²·nm⁻¹ for absolute EDI.

**`circadian_metrics(channels, channel_type = 1, spd = null)`** — channels → `photopic_lux`,
`melanopic_lux`, `neuropic_lux`, **`mel_edi`**, **`mel_der`**, `mel_der_source` (+ `mel_der_note` on the
binned route). One dict for one point, a list of dicts for many.

> **⚠️ `melanopic_lux` is NOT mel-EDI — use `mel_edi` for every standards check.** `melanopic_lux` is a
> melanopic-weighted illuminance; CIE S 026 mel-EDI is `photopic_lux × mel-DER`. They differ by D65's own
> binned melanopic/photopic ratio, **1.099665** (~9%), and **that is enough to flip a verdict**: a kit eye
> point reading `melanopic_lux` 260.65 "passes" Brown's ≥250 lx, while its true mel-EDI of 237.03 **fails**.
> `compliance` stamps `quantity` on every result so an artifact can't be ambiguous afterwards.
>
> **Accuracy:** without `spd`, mel-DER is inferred from the binned channels — exact for D65, ~0.1% for
> daylight, but up to ~8% high for a narrow-band fluorescent whose lines fall inside one bin. Pass
> `spd=<source spectrum>` for the exact S 026 value; `mel_der_source` records which route was used.

**`spectral_metrics(spd = null, metric = "all", eml_edi_value = null, eml_edi_direction = "medi_to_eml")`**

| Param                 | Default         | What it does                                                                                              |
| --------------------- | --------------- | --------------------------------------------------------------------------------------------------------- |
| `spd`               | `null`        | SPD (`.spd` path, text, or list of `[wl,val]`) →`{cct_duv, mel_der, mel_photopic_ratio, eml_edi}`. |
| `metric`            | `all`         | Return one block instead of all:`cct_duv` · `mel_der` · `mel_photopic_ratio` · `eml_edi`.      |
| `eml_edi_value`     | `null`        | Scalar EML↔mel-EDI conversion**without** an SPD (mutually exclusive with `spd`).                 |
| `eml_edi_direction` | `medi_to_eml` | Direction of that scalar conversion:`medi_to_eml` or `eml_to_medi`.                                   |

**`compliance(mel_edi = null, eml = null, standard = "brown_2022", period = "daytime", daylight_met = false)`**

| Param                      | Default        | What it does                                                                                                    |
| -------------------------- | -------------- | --------------------------------------------------------------------------------------------------------------- |
| `mel_edi` *or* `eml` | —             | The value to judge (give one).                                                                                  |
| `standard`               | `brown_2022` | `brown_2022` · `well_v2_l03` · `iso_cie_8995_1_2025` · `en_17037` · `en_12464_1` · `ul_24480`. |
| `period`                 | `daytime`    | `daytime`(≥250) · `evening`(≤10) · `sleep`(≤1) · `night`(≤10).                                   |
| `daylight_met`           | `false`      | For`en_17037`: whether the daylight-provision sub-criterion is already met.                                   |

**`reconstruct_spectrum(sky_channels, sun_channels, channel_type = 1, method = "reference", sky_spd = null, sun_spd = null, sun_spectral = "colored", solar_zenith = null, dseries_sky = false, sky_cct = null)`**

| Param                              | Default       | What it does                                                                                                                             |
| ---------------------------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `sky_channels`, `sun_channels` | —            | The binned sky-diffuse and sun-direct channel sets to expand to a 401-pt 380–780 nm spectrum.                                           |
| `method`                         | `reference` | `reference` = reference-SPD-shaped sky + air-mass sun, re-integrated to bins. `faithful` = legacy flat step-expansion + neutral sun. |
| `sun_spectral`                   | `colored`   | `colored` = air-mass solar SPD by `solar_zenith`; `neutral` = flat.                                                                |
| `solar_zenith`                   | `null`      | Zenith angle (deg) driving the colored-sun air mass.                                                                                     |
| `dseries_sky`                    | `false`     | `true` = reconstruct a per-timestep CIE D-series sky from `sky_cct`.                                                                 |
| `sky_cct`                        | `null`      | Sky CCT for the D-series option.                                                                                                         |
| `sky_spd`, `sun_spd`           | `null`      | Optional 401-value physical references that override the templates.                                                                      |

> Always returns the flat-vs-reference and neutral-vs-colored-sun `divergence` so you see how much
> the method choice matters.

**`reference(topic = "overview")`** — `overview` · `coefficients` · `bins` · `caveats`.

**`glass_transmissivity(transmittance)`** — a number or list of glazing transmittances (0–1) → Radiance transmissivity.

### B.3 — Geometry, materials, sky (group B)

**`import_geometry(obj_path, material_map = null, units = null, up_axis = null, channel_type = 1, north_angle_deg = null, dry_run = false, sidecar = null, derive_sensors = false, annotate = false, eye_heights = null, workplane_h = 0.8, spacing = 0.6, run = true, work_dir = null)`**

| Param               | Default                      | What it does                                                                                                                                                                                                                                               |
| ------------------- | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `obj_path`        | —                           | Path to the Wavefront`.obj`.                                                                                                                                                                                                                             |
| `material_map`    | `null`                     | `{group: spec}` for **every** OBJ group (an unmapped group hard-fails). `spec` = a library-name string, or a dict `{"type": plastic\|glass\|ground\|context\|luminaire\|floor, "refl"\|"tvis"\|"spd"\|"ies": …}`. Not required when `dry_run=true`. |
| `units`           | `null`                     | `mm`·`cm`·`m`·`ft` (a bbox sanity-check warns on a wrong guess).                                                                                                                                                                                |
| `up_axis`         | `null`                     | `Y`·`Z`.                                                                                                                                                                                                                                              |
| `north_angle_deg` | `null`                     | **Set this for any daylight/annual run** — clockwise azimuth (0=N, 90=E) that the model's +Y faces. Omitting it silently assumes +Y = true north.                                                                                                   |
| `dry_run`         | `false`                    | `true` = return discovery only (groups, bbox, mesh quality, suggestions); no materials, no Radiance.                                                                                                                                                     |
| `sidecar`         | `null`                     | Path to a`*.matmap.json` supplying defaults (explicit kwargs win).                                                                                                                                                                                       |
| `derive_sensors`  | `false`                    | `true` = also return `grid_points` (work-plane), `observer_sets`/`observer_points` (eye-level, both seated & standing), and `glare_views`.                                                                                                       |
| `annotate`        | `false`                    | `true` = also render a colored-by-material falsecolor image.                                                                                                                                                                                             |
| `eye_heights`     | `null` (→ `[1.2, 1.6]`) | Eye-level heights (m) for derived observers.                                                                                                                                                                                                               |
| `workplane_h`     | `0.8`                      | Work-plane height (m) for the derived grid.                                                                                                                                                                                                                |
| `spacing`         | `0.6`                      | Sensor spacing (m) for the derived grid.                                                                                                                                                                                                                   |

> The next four tools (`workplane_grid`, `observer_points`, `photosensors`, `preview_scene`) all read
> an OBJ the same way `import_geometry` does, so they share these five loader kwargs — described once
> here, not repeated below: **`material_map`** (or **`sidecar`** — either supplies the group→material map
> so the room's interior can be found), **`units`**, **`up_axis`**, **`north_angle_deg`**. Each also
> takes **`work_dir`** (see §B.0). The methodology behind them is walked through in
> [§5.3.4a](#534a--dedicated-sensor-tools-workplane_grid-observer_points-photosensors).

**`workplane_grid(obj_path, material_map = null, sidecar = null, units = null, up_axis = null, north_angle_deg = null, workplane_h = 0.8, border_offset = 0.25, max_spacing = null, wall_thickness = null, interior_extent = null, clip_to_footprint = true, footprint_border = 0.0, write_pts = "grid.pts", work_dir = null)`** — EN 12464-1 work-plane illuminance grid, incl. concave (L/T/U) rooms.

| Param                 | Default      | What it does                                                                                 |
| --------------------- | ------------ | -------------------------------------------------------------------------------------------- |
| `obj_path`          | —           | Path to the Wavefront`.obj`. (+ shared loader kwargs above.)                               |
| `workplane_h`       | `0.8`      | Grid height (m) above the floor — the EN 12464-1 task plane.                                |
| `border_offset`     | `0.25`     | Margin (m) kept clear of the walls (EN 12464-1 border band).                                 |
| `max_spacing`       | `null`     | Max cell size (m).`null` = derived from room size per the EN max-spacing rule.             |
| `wall_thickness`    | `null`     | Hint (m) for detecting the innermost wall face when auto-finding the interior.               |
| `interior_extent`   | `null`     | `[xmin,xmax,ymin,ymax]` to pin the grid rectangle explicitly instead of auto-detecting it. |
| `clip_to_footprint` | `true`     | `true` = drop grid cells that fall outside the room's floor footprint (concave rooms).     |
| `footprint_border`  | `0.0`      | Extra inward margin (m) applied when clipping to the footprint.                              |
| `write_pts`         | `grid.pts` | Output`.pts` filename (set `null` to skip writing).                                      |

**`observer_points(obj_path, material_map = null, sidecar = null, units = null, up_axis = null, north_angle_deg = null, eye_height = 1.2, seat_pattern = "(?i)chair.*seat|seat", screen_pattern = "(?i)disp.*panel|screen|monitor|display", direction_fallback = "window", fallback_azimuth = null, sweep_n = 8, workstations = null, position_fallback = "room_center", clip_to_footprint = true, write_pts = "observers.pts", work_dir = null)`** — workstation eye sensors (vertical, at the eye) + matching `glare_views`.

| Param                  | Default           | What it does                                                                                                                              |
| ---------------------- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `obj_path`           | —                | Path to the`.obj`. (+ shared loader kwargs above.)                                                                                      |
| `eye_height`         | `1.2`           | Eye height (m); a single number**or** a list for several heights (e.g.`[1.2, 1.6]` seated & standing).                            |
| `seat_pattern`       | seat regex        | Regex matching OBJ group names that mark a seat/chair (where an observer sits).                                                           |
| `screen_pattern`     | screen regex      | Regex matching monitor/display groups (used to aim the gaze).                                                                             |
| `direction_fallback` | `window`        | How to face an observer with no screen:`window` (toward the aperture) · `azimuth` (use `fallback_azimuth`) · `sweep` (N views). |
| `fallback_azimuth`   | `null`          | Gaze azimuth (deg) when`direction_fallback="azimuth"`.                                                                                  |
| `sweep_n`            | `8`             | Number of views generated per observer when`direction_fallback="sweep"`.                                                                |
| `workstations`       | `null`          | Explicit`[{pos, dir}, …]` list to bypass seat/screen detection entirely.                                                               |
| `position_fallback`  | `room_center`   | Where to place an observer when no seat is found:`room_center`, or an explicit `[x,y]` / list.                                        |
| `clip_to_footprint`  | `true`          | Verify each observer lands inside the room footprint.                                                                                     |
| `write_pts`          | `observers.pts` | Output`.pts` filename (set `null` to skip).                                                                                           |

**`photosensors(obj_path, material_map = null, sidecar = null, units = null, up_axis = null, north_angle_deg = null, zone_rule = "head_height", depth_factors = null, sensor_fraction = 0.667, task_height = 0.0, mount = "workplane", workplane_h = 0.8, write_pts = "photosensors.pts", work_dir = null)`** — daylight-dimming reference sensors (pure Python, no engine).

| Param               | Default              | What it does                                                                                          |
| ------------------- | -------------------- | ----------------------------------------------------------------------------------------------------- |
| `obj_path`        | —                   | Path to the`.obj`. (+ shared loader kwargs above.)                                                  |
| `zone_rule`       | `head_height`      | How deep the daylit zone reaches:`head_height` · `ies_2.5` (2.5× window-head height, IES rule). |
| `depth_factors`   | `null`             | Explicit list of depth multipliers to override`zone_rule`.                                          |
| `sensor_fraction` | `0.667` (2/3)      | Fraction into each zone (from the façade) where the sensor sits.                                     |
| `task_height`     | `0.0`              | Task-plane height (m) referenced by the zone rule.                                                    |
| `mount`           | `workplane`        | Sensor mounting:`workplane` (at `workplane_h`) · `ceiling` (photocell on the ceiling).         |
| `workplane_h`     | `0.8`              | Work-plane height (m) when`mount="workplane"`.                                                      |
| `write_pts`       | `photosensors.pts` | Output`.pts` filename (set `null` to skip).                                                       |

**`preview_scene(obj_path, material_map = null, sidecar = null, units = null, up_axis = null, north_angle_deg = null, render = "all", grid_pts = null, observer_pts = null, photosensor_pts = null, luminaire_groups = null, write_prefix = "preview", work_dir = null)`** — matplotlib PNG scene previews (diagnostic sanity-check, **not** photometric).

| Param                | Default     | What it does                                                                                                   |
| -------------------- | ----------- | -------------------------------------------------------------------------------------------------------------- |
| `obj_path`         | —          | Path to the`.obj`. (+ shared loader kwargs above.)                                                           |
| `render`           | `all`     | Which view(s):`all` · `grid` (plan) · `observers` (plan w/ gaze arrows) · `observers_3d` (mplot3d). |
| `grid_pts`         | `null`    | Grid points to overlay — a`.pts` path **or** inline `[x,y,z,dx,dy,dz]` rows.                        |
| `observer_pts`     | `null`    | Observer points to overlay (same shape as`grid_pts`).                                                        |
| `photosensor_pts`  | `null`    | Photosensor points to overlay (same shape).                                                                    |
| `luminaire_groups` | `null`    | OBJ group names to draw as luminaires.                                                                         |
| `write_prefix`     | `preview` | Output filename stem;`image_paths` are `<prefix>_<render>.png`.                                            |

**`write_material(channels, material_type, channel_type, name, roughness = 0.0, specularity = 0.0, work_dir = null)`**

| Param             | Default | What it does                                                                |
| ----------------- | ------- | --------------------------------------------------------------------------- |
| `channels`      | —      | Channel values describing the surface's spectral reflectance/transmittance. |
| `material_type` | —      | `0`=glass (transmitting) · `1`=plastic (opaque diffuse).               |
| `channel_type`  | —      | `0` or `1` (must match `channels`).                                   |
| `name`          | —      | Material name (also the output`.rad` filename stem).                      |
| `roughness`     | `0.0` | Radiance surface roughness.                                                 |
| `specularity`   | `0.0` | Specular fraction (0 = matte).                                              |

**`colored_sky(diffuse_channels, direct_channels, channel_type = 1, month = 6, day = 21, hour = 12.0, irrad_mode = "W", mode = "spectra", lat = 0.0, lon = 0.0, utc = 0, direct = null, diffuse = null, globl = null, name = "sky", work_dir = null, run = true)`**

| Param                                     | Default       | What it does                                                                                                                      |
| ----------------------------------------- | ------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `diffuse_channels`, `direct_channels` | —            | 3- or 9-channel values (from`spd_to_channels`) that color the sky vault and the solar disc. Ignored in `luminance` mode.      |
| `month`/`day`/`hour`                | `6/21/12.0` | The sun position's date and (decimal) hour.                                                                                       |
| `lat`/`lon`/`utc`                   | `0/0/0`     | Site latitude, longitude, UTC offset — set these for a real location.                                                            |
| `irrad_mode`                            | `W`         | `W` = supply `direct`+`diffuse`; `E` = supply `globl` (global).                                                         |
| `mode`                                  | `spectra`   | `spectra` = per-channel spectral scaling (runs gendaylit). `luminance` = Radiance `-C` built-in coloring (3-ch, pure emit). |
| `direct`/`diffuse`/`globl`          | `null`      | Irradiance magnitudes (W). Use`direct`+`diffuse` with `irrad_mode="W"`, or `globl` with `"E"`.                          |
| `name`                                  | `sky`       | Output`.rad` stem.                                                                                                              |

**`colored_luminaire(rad_path, channels9, count, name = null, work_dir = null)`** — inject the
`count`-th third (`0`=blue, `1`=green, `2`=red) of a 9-channel set into a luminaire `.rad`; writes a
**new** file, never edits the input.

**`radiance_status()`** — no parameters → `{available, bin_dir, version, found, missing}`.

### B.4 — Simulation: grid, image, glare (group C)

**`run_grid(scene_sets, points, channel_type = 1, rad_params = null, work_dir = null, run = true, export_csv = null, electric_lights = null)`**

| Param                                                           | Default  | What it does                                                                                                                                    |
| --------------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `scene_sets`                                                  | —       | 1 list of`.rad` paths (3-ch) or 3 lists (9-ch, blue/green/red).                                                                               |
| `points`                                                      | —       | `[x,y,z,dx,dy,dz]` rows or a `.pts` path.                                                                                                   |
| `export_csv`                                                  | `null` | Path to dump the per-point result table.                                                                                                        |
| `electric_lights`                                             | `null` | Drop-in luminaire payload (from`import_geometry` or `ies_to_radiance`) — adds the electric contribution; the tool runs ies2rad + colorize. |
| *(+ `rad_params`, `work_dir`, `run`, `channel_type`)* |          | See §B.0.                                                                                                                                      |

**`run_image(scene_sets, channel_type = 1, view = "-vta -vh 180 -vv 180", x = 800, y = 800, rad_params = null, fov_weighting = false, mask_dir = null, electric_lights = null, glare = false, glare_params = null, work_dir = null, run = true)`**

| Param               | Default                  | What it does                                                                                 |
| ------------------- | ------------------------ | -------------------------------------------------------------------------------------------- |
| `view`            | `-vta -vh 180 -vv 180` | rpict view — the default is a 180° fisheye. Reuse a`glare_views` string from the import. |
| `x` / `y`       | `800` / `800`        | Output resolution (px).                                                                      |
| `fov_weighting`   | `false`                | `true` = apply the ipRGC field-of-view weighting to the eye irradiance.                    |
| `mask_dir`        | `null`                 | Folder of FOV mask images to override the built-in weighting.                                |
| `electric_lights` | `null`                 | Add electric fixtures to the render (same payload shape as`run_grid`).                     |
| `glare`           | `false`                | `true` = also run evalglare (this is what `glare_ugr` does internally).                  |
| `glare_params`    | `null`                 | Extra evalglare flags.                                                                       |

**`glare_ugr(scene_sets, channel_type = 0, view = "-vta -vh 180 -vv 180", electric_lights = null, x = 800, y = 800, rad_params = null, glare_params = null, work_dir = null, run = true)`** — same knobs as
`run_image` but **defaults `channel_type=0`** and always runs evalglare → `{UGR, DGP, glare_sources}`.

### B.5 — Electric lighting & energy (group D)

**`ies_analyze(ies)`** — raw IES text or a path → photometric report.

**`ies_to_radiance(ies, placement = null, color = null, lamp = null, units = 2, units_divisor = null, multiplier = 1.0, maintenance_factor = 1.0, out_prefix = null, work_dir = null, run = true)`**

| Param                  | Default  | What it does                                                                                                          |
| ---------------------- | -------- | --------------------------------------------------------------------------------------------------------------------- |
| `ies`                | —       | IES text or path.                                                                                                     |
| `placement`          | `null` | Where to put fixtures, e.g.`{"grid":{rows,cols,row_spacing,col_spacing,origin}}` or explicit positions (via xform). |
| `color`              | `null` | Optional channel triplet to tint the luminaire.                                                                       |
| `lamp`               | `null` | ies2rad lamp type / color name.                                                                                       |
| `units`              | `2`    | `2`=meters, `1`=feet (ies2rad `-d`).                                                                            |
| `units_divisor`      | `null` | Override the geometry scaling divisor.                                                                                |
| `multiplier`         | `1.0`  | User flux scaling (combined with`maintenance_factor` into ies2rad `-m`).                                          |
| `maintenance_factor` | `1.0`  | Light-loss factor (× into the same`-m`).                                                                           |
| `out_prefix`         | `null` | Output filename stem.                                                                                                 |

**`recommend_fixtures(length_m, width_m, height_m, mount_height_m, workplane_height_m = 0.8, eye_height_m = 1.2, rho_ceiling = 0.7, rho_wall = 0.5, rho_floor = 0.2, maintenance_factor = 0.8, target_em_lux = 500.0, target_mel_edi = null, mel_edi_daylight = 0.0, vertical_horizontal_ratio = 0.4, distribution = "direct", target_efficacy_lm_w = 120.0)`**

| Param                                      | Default                 | What it does                                                                             |
| ------------------------------------------ | ----------------------- | ---------------------------------------------------------------------------------------- |
| `length_m`/`width_m`/`height_m`      | —                      | Room dimensions.                                                                         |
| `mount_height_m`                         | —                      | Luminaire mounting height.                                                               |
| `workplane_height_m` / `eye_height_m`  | `0.8` / `1.2`       | Heights for the visual and circadian planes.                                             |
| `rho_ceiling`/`rho_wall`/`rho_floor` | `0.7`/`0.5`/`0.2` | Surface reflectances (drive the utilisation factor).                                     |
| `maintenance_factor`                     | `0.8`                 | Light-loss factor.                                                                       |
| `target_em_lux`                          | `500.0`               | Visual task target (horizontal lux).                                                     |
| `target_mel_edi`                         | `null`                | Circadian target (vertical mel-EDI at the eye). Omit to size for the visual target only. |
| `mel_edi_daylight`                       | `0.0`                 | Daylight mel-EDI already present — credits the circadian budget (not the visual flux).  |
| `vertical_horizontal_ratio`              | `0.4`                 | V/H ratio (the dominant uncertainty in the circadian solve).                             |
| `distribution`                           | `direct`              | `direct` · `direct_indirect` · `indirect`.                                       |
| `target_efficacy_lm_w`                   | `120.0`               | Assumed luminaire efficacy for the energy estimate.                                      |

> Sizing is first-principles / illustrative — a plausibility check, not a verdict. Confirm with a real IES.

**`lighting_controls(itot_per_point = null, itot_series = null, weights = null, iset = 500.0, control_type = "ContinuousOff", fP_min = 0.15, fL_min = 0.05, n_steps = 3, p_rated = 448.0, schedule = null, area = null, workbook_compat = false)`**

| Param                   | Default             | What it does                                                                                      |
| ----------------------- | ------------------- | ------------------------------------------------------------------------------------------------- |
| `itot_per_point`      | `null`            | Point-in-time: lux at each reference point →`{fL, fP, FP, P_elec, P_saved, reduction}`.        |
| `itot_series`         | `null`            | Annual:`[[lux per point] per hour]` (with `area`) → `{annual_kwh, annual_kwh_per_m2, …}`. |
| `weights`             | `null`            | Per-point area weights.                                                                           |
| `iset`                | `500.0`           | Setpoint illuminance the control aims to maintain.                                                |
| `control_type`        | `ContinuousOff`   | `ContinuousOff` · `Continuous` · `Stepped`.                                               |
| `fP_min` / `fL_min` | `0.15` / `0.05` | Minimum dimmed power fraction / minimum light fraction.                                           |
| `n_steps`             | `3`               | Number of steps for`Stepped`.                                                                   |
| `p_rated`             | `448.0`           | Rated installed power (W).                                                                        |
| `schedule`            | `null`            | Occupancy schedule (scalar or per-hour list).                                                     |
| `area`                | `null`            | Floor area (m²) — needed for the annual kWh/m².                                                |
| `workbook_compat`     | `false`           | Reproduce the`elec_lights.xlsx` off-gates (regression mode).                                    |

**`daylight_savings(scene_sets = null, channel_scenes = null, points = null, sensor_set = null, wea = null, channel_type = 1, weights = null, mode = "point_in_time", iset = 500.0, control_type = "ContinuousOff", fP_min = 0.15, fL_min = 0.05, n_steps = 3, p_rated = 448.0, area = null, schedule = null, workbook_compat = false, rad_params = null, work_dir = null, run = true)`** — runs the daylight sim then `lighting_controls`. `mode="point_in_time"` uses `scene_sets`+`points` (`run_grid`); `mode="annual"` uses `channel_scenes`+`wea`+`points`/`sensor_set` (the annual daylight runner, 8760 h — confirms before the long run) and supports a **multi-point grid** in one call (one `weights` entry — a floor-area fraction, Σ≤1 — per point; defaults to uniform 1/n). The control knobs (`iset`…`workbook_compat`) match `lighting_controls`.

### B.6 — Weather, annual & alertness (group E)

**`weather(wea_path = null, period = null, timestep_min = 60, subset_out = null)`**

| Param            | Default  | What it does                                                    |
| ---------------- | -------- | --------------------------------------------------------------- |
| `wea_path`     | `null` | The`.wea` to ingest → `wea_summary` (counts, ranges).      |
| `period`       | `null` | `[[m,d,h],[m,d,h]]` to decompose into HOY + wea line numbers. |
| `timestep_min` | `60`   | Sub-hour timestep for the decomposition.                        |
| `subset_out`   | `null` | Path to write the subset`.wea` for the period.                |

**`run_annual(channel_scenes, wea, points, channel_type = 1, rad_params = null, dosimetry_threshold = 250.0, period = null, timestep_min = 60, work_dir = null, run = true)`**

| Param                   | Default   | What it does                                                                                                                                        |
| ----------------------- | --------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `channel_scenes`      | —        | 1 dict (3-ch) or 3 dicts (9-ch), each`{materials:[paths], geometry:<one .rad>, sky_color:[r,g,b]}`. Note `geometry` is a **single** path. |
| `wea`                 | —        | The annual`.wea`.                                                                                                                                 |
| `points`              | —        | Inline rows or a`.pts` (the meaningful circadian sensor is vertical, at the eye).                                                                 |
| `dosimetry_threshold` | `250.0` | mel-EDI lux above which hours are counted.                                                                                                          |
| `period`              | `null`  | `[[m,d,h],[m,d,h]]` — **always pass a tight window** for speed; omit = full year.                                                          |
| `timestep_min`        | `60`    | Sub-hour timestep.                                                                                                                                  |

**`annual_daylight(channel_scenes, wea, points = null, sensor_set = null, channel_type = 1, rad_params = null, da_threshold = 300.0, udi_lower = 100.0, udi_sup = 300.0, udi_aut = 3000.0, sda_da_fraction = 0.5, ase_threshold = 1000.0, ase_hours = 250.0, occupancy = null, occupied_start = 8, occupied_end = 18, timestep_min = 60, work_dir = null, run = true)`** — climate-based daylight metrics on the grid.

| Param                                 | Default                  | What it does                                                                                       |
| ------------------------------------- | ------------------------ | -------------------------------------------------------------------------------------------------- |
| `channel_scenes` / `wea`          | —                       | Same shape as`run_annual` (`{materials,geometry,sky_color}`; annual `.wea`).                 |
| `points` / `sensor_set`           | `null`                 | Inline rows /`.pts`, **or** a named set from the `sensors` tool (a `sensor_set` wins). |
| `da_threshold`                      | `300.0`                | DA/cDA illuminance threshold (lx).                                                                 |
| `udi_lower`/`udi_sup`/`udi_aut` | `100`/`300`/`3000` | The four UDI bin edges (short / supplementary / autonomous / exceed), in lx.                       |
| `sda_da_fraction`                   | `0.5`                  | DA fraction a point must clear to count toward sDA (0.5 → sDA300/50%).                            |
| `ase_threshold`/`ase_hours`       | `1000`/`250`         | Direct-sun lux + occupied-hour count defining ASE (its own direct-only`-ab 0` pass).             |
| `occupancy`                         | `null`                 | Per-timestep 0/1 mask; else weekday`occupied_start`..`occupied_end`, Monday-anchored 8760-h.   |

> No `period`/`partial_year` at the tool level yet — it always simulates the full 8760-hour year.

**`daylight_factor(scene_sets, points = null, sensor_set = null, rad_params = null, month = 6, day = 21, hour = 12.0, gnd_refl = 0.2, work_dir = null, run = true)`** — Daylight Factor % per point under a CIE Standard Overcast Sky (`gensky -c`). `E_outdoor` is traced from a sky-only exterior reference (not an assumed constant); month/day/hour only fix the sun-free dome's solar geometry. Returns `df_per_point`, `df_avg`, `df_min`, `uniformity` (`df_min/df_avg`), `e_outdoor`. `scene_sets` is the building (materials+geometry) as one 3-channel list; the overcast sky is added internally.

**`sensors(action, name = null, points = null, grid = null, overwrite = false, work_dir = null)`** — manage named persistent sensor sets so `annual_daylight`/`daylight_factor`/`daylight_savings` can reuse them via `sensor_set="name"`. `action`: `create` (`name` + `points=[[x,y,z,dx,dy,dz],…]` **or** `grid={interior:[xmin,xmax,ymin,ymax], floor_z, workplane_h?, max_spacing?}` for an EN 12464-1 grid; `overwrite=true` to replace) · `list` · `get` · `delete`. Sets persist under `work_dir` as `.pts` files + a JSON registry.

**`nvrd(spectral_series, timestep_h = 0.1, hours = null)`**

| Param               | Default  | What it does                                                                                       |
| ------------------- | -------- | -------------------------------------------------------------------------------------------------- |
| `spectral_series` | —       | Per-timestep spectral irradiance rows (311 or 401 pts),**single** point+view, chronological. |
| `timestep_h`      | `0.1`  | Hours/step — must be ≤ 0.3 and give odd filter lengths;`0.1` (6 min) is the validated value.   |
| `hours`           | `null` | Explicit non-uniform hour vector (monotonic); omit for a uniform grid.                             |

**`daysim_status()`** — no parameters.

**`build_daysim(src_dir = null, run = true, work_dir = null)`** — clone + headless CMake build of `ds_shortterm`+`epw2wea`; `run=false` returns the command plan.

**`generate_subhourly_wea(epw, timestep_min = 6, latitude = null, longitude = null, time_zone = null, site_elevation = null, solar_time = 0, work_dir = null, run = true)`**

| Param                                                       | Default  | What it does                                                                                                                                                                                        |
| ----------------------------------------------------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `epw`                                                     | —       | The hourly EPW to upsample.                                                                                                                                                                         |
| `timestep_min`                                            | `6`    | Sub-hour step (0.1 h) — keep the default for the nvRD guard.                                                                                                                                       |
| `latitude`/`longitude`/`time_zone`/`site_elevation` | `null` | **Override only** — defaults come from the EPW LOCATION line. If you do override, use the DAYSIM convention (**west-positive** longitude, time_zone in **degrees** = −15×UTC). |
| `solar_time`                                              | `0`    | `1` = treat timestamps as solar time.                                                                                                                                                             |

**`annual_nvrd(point_xyz, view_vec, epw = null, channel_scenes = null, points = null, channel_type = 1, timestep_min = 6, reconstruction = "both", sky_reconstruction = "reference", sun_spectral = "colored", sky_cct = null, rad_params = null, work_dir = null, run = true, physical_sky = false, engine = "spectrl2")`**

| Param                           | Default       | What it does                                                                                                                                                                                                |
| ------------------------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `point_xyz` / `view_vec`    | —            | The single sensor position and gaze direction.                                                                                                                                                              |
| `epw`                         | `null`      | Weather (drives the sub-hourly`.wea`).                                                                                                                                                                    |
| `channel_scenes` / `points` | `null`      | Required for**both** live and emit paths (the plan is built from real per-channel transport). `points` takes inline `[x,y,z,dx,dy,dz]` rows or a `.pts` path (same contract as `run_annual`). |
| `timestep_min`                | `6`         | Sub-hour step (≤15 for nvRD).                                                                                                                                                                              |
| `reconstruction`              | `both`      | `both` · `faithful` · `enhanced` — which R_D series to return.                                                                                                                                     |
| `sky_reconstruction`          | `reference` | `reference` (static shape) · `dseries` (per-timestep CIE D-series from `sky_cct`).                                                                                                                   |
| `sun_spectral`                | `colored`   | `colored` · `neutral`.                                                                                                                                                                                 |
| `physical_sky`                | `false`     | `true` = shape the *enhanced* reconstruction with physical EPW-derived spectra (opt-in, not yet live-validated).                                                                                        |
| `engine`                      | `spectrl2`  | `spectrl2` · `smarts` — only used when `physical_sky=true`.                                                                                                                                         |

> `R_D` is **relative** — compare scenarios, never read it as an absolute dose.

### B.7 — Physical spectral sky from EPW (group F)

**`atmosphere_from_epw(epw, month, day, hour, ozone_mode = null, aerosol_g = null, aod_anchor_nm = null)`** — EPW hour → `{aod500, pw_cm, ozone_atm_cm, pressure_mbar, albedo, aerosol_g, provenance}`. The last three args are **opt-in atmosphere refinements**; each defaults to the pre-refinement (byte-identical) output.

| Param             | Default  | What it does                                                                                                                            |
| ----------------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `ozone_mode`    | `null` (`"constant"`) | `"climatology"` computes a **van Heuklon 1979** ozone column from the EPW LOCATION lat/lon + date (hemisphere-specific, NH spring-max); default `"constant"` keeps 0.30 atm-cm. |
| `aerosol_g`     | `null` (`0.65`) | Aerosol asymmetry `g` (D-7) — consumed by SPECTRL2 + the single-scatter façade colour.                                              |
| `aod_anchor_nm` | `null`   | Ångström-convert a declared-wavelength AOD (e.g. `550`) to τ₅₀₀ (D-3); `null`/`500` is a no-op.                                    |

**`spectral_sky_from_epw(epw, month, day, hour, overrides = null, surface_tilt_deg = null, engine = "spectrl2", spectral_albedo = null, ozone_mode = null, aerosol_g = null, aod_anchor_nm = null, smarts_aerosol = null)`**

| Param                      | Default      | What it does                                                                                                    |
| -------------------------- | ------------ | --------------------------------------------------------------------------------------------------------------- |
| `month`/`day`/`hour` | —           | The target moment.                                                                                              |
| `overrides`              | `null`     | Dict to override any derived atmosphere input (AOD/PWV/ozone/…).                                               |
| `surface_tilt_deg`       | `null`     | Receiver tilt (90 = vertical window) — adds the spectral ground-glow term.                                     |
| `engine`                 | `spectrl2` | `spectrl2` (pure Python) · `smarts` (needs `$SMARTSPATH`).                                               |
| `spectral_albedo`        | `null`     | 401-value ground albedo (e.g.`import_geometry(...)["ground_albedo"]`) to couple scene ground to the sky glow. |
| `ozone_mode`/`aerosol_g`/`aod_anchor_nm` | `null` | Opt-in atmosphere refinements (as in `atmosphere_from_epw` above); defaults reproduce prior output.        |
| `smarts_aerosol`         | `null` (`"rural"`) | `"user"` makes the SMARTS Ångström α + `g` settable (`AEROS='USER'` Card 8a, D-20; `engine="smarts"` only); default `"rural"` keeps the `S&F_RURAL` deck. |

**`spectral_epw(epw, forms = null, hours = null, work_dir = null, engine = "spectrl2", ozone_mode = null, aerosol_g = null, aod_anchor_nm = null, smarts_aerosol = null)`**

| Param      | Default          | What it does                                                                    |
| ---------- | ---------------- | ------------------------------------------------------------------------------- |
| `forms`  | `null` (= all) | Any subset of`spd_set` · `band_matrix` · `spectral_wea` · `sidecar`. |
| `hours`  | `null`         | List of`[month, day, hour]` to subset (a full year is long-running).          |
| `engine` | `spectrl2`     | `spectrl2` · `smarts`.                                                     |
| `ozone_mode`/`aerosol_g`/`aod_anchor_nm`/`smarts_aerosol` | `null` | Same opt-in refinements as `spectral_sky_from_epw`; the annual path applies ozone climatology **per-row** (season-varying). |

**`spectral_sky_native(epw, mf = 1, mode = "all", work_dir = null, run = true, timeout = null)`**

| Param       | Default  | What it does                                                                                                                                                                                 |
| ----------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `mf`      | `1`    | Reinhart sky subdivision factor (MF:1 = 145 patches).                                                                                                                                        |
| `mode`    | `all`  | `all` · `sun` (`-d`) · `sky` (`-s`).                                                                                                                                             |
| `timeout` | `null` | Seconds cap on gensdaymtx (it processes**every** EPW hour — trim the EPW or set this; ~10+ min for a full year). On expiry returns `{ok:false, timed_out:true}` instead of raising. |

### B.8 — Study brief & report (group G)

**`load_brief(study, work_dir = null)`** — load (or start an empty) brief for the study slug.

**`save_brief(study, brief, work_dir = null)`** — shallow-merge-save the brief (call after each phase).

**`build_report(study, brief, work_dir = null)`** — render `report.{md,html}` (goal recap, fixture spec,
target-vs-achieved pass/fail, circadian↔glare cross-check, compliance).

> **End-to-end pointer:** the prompts in §5.3 chain these tools for you; this appendix is for when you
> want to call one directly and need a knob the prompt didn't surface. The science behind the numbers
> is in **Part 6**; what to *type* is in **§5.7**.
