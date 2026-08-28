# Onboarding — Claude Code setup for contributors

**About this project:** `tack` is a dev-mode-only visual editor for positioning decorative elements on a live Next.js portfolio — drag/rotate/scale/multi-select on the page, then Save writes the new positions back into a TypeScript config file via `ts-morph`. See `CLAUDE.md` for the stack and `plan/0_plan.md` for full architecture; the repo is currently spec-only (no source code yet, see `plan/` for the phase-by-phase build order).

This project uses [claude-start](https://github.com/moneytosms/claude-start) to give Claude Code shared memory, hooks, agents, and commands that work the same for every contributor.

This doc takes about 10 minutes. Do it once when you first clone the repo.

---

## 1. Prerequisites

| Tool | Version | Why |
|---|---|---|
| [Claude Code](https://claude.ai/code) | Latest | The AI coding assistant this is all built on |
| [Node.js](https://nodejs.org) | 18+ | Required by Claude Code and ctx7 |
| [Rust / Cargo](https://rustup.rs) | Stable | Required by RTK (token compression) |
| [GitHub CLI](https://cli.github.com) | Any | Used by `/commit`, `/pr`, `/ship` |

---

## 2. Set up your local settings

Create `.claude/settings.local.json` in the project root (it's gitignored — never commit it):

```bash
cp .claude/settings.local.json.example .claude/settings.local.json
```

Then open it and set:

```json
{
  "env": {
    "PROJECT_FMT": "prettier --write",
    "NODE_ENV": "development"
  }
}
```

Set `PROJECT_FMT` to whatever formatter this project uses. Check `CLAUDE.md` → **Format** for the right command. If there's no formatter, leave it empty.

---

## 3. Install the plugins (first time only, per machine)

These are global Claude Code plugins — install once and they apply to all your projects:

```bash
claude plugin marketplace add addyosmani/agent-skills
claude plugin marketplace add JuliusBrussee/caveman
claude plugin marketplace add DietrichGebert/ponytail
npx skills@latest add mattpocock/skills
# Select: grill-me, handoff, tdd, git-guardrails-claude-code, write-a-skill
```

Also install RTK (token compression):
```bash
cargo install --git https://github.com/rtk-ai/rtk
rtk init -g
```

---

## 4. Make hooks executable (macOS / Linux / WSL only)

```bash
chmod +x .claude/hooks/*.sh
```

On Windows, hooks run via WSL. The hook commands in `settings.json` use `wslpath` to convert Windows paths to WSL paths automatically — no manual setup needed beyond having WSL installed.

---

## 5. What's in `.claude/` and why it matters to you

```
.claude/
├── settings.json          ← Committed. Shared hooks, permissions, model. Don't edit locally.
├── settings.local.json    ← Yours only. Gitignored. Set PROJECT_FMT here.
├── CLAUDE.md              ← Project memory. Claude reads this every session.
├── agents/                ← Subagent definitions (ReadOnly, BuildValidator, etc.)
├── commands/              ← Slash commands (/plan, /ship, /review, etc.)
├── hooks/                 ← Scripts that run automatically on Claude events (incl. statusline.sh)
├── rules/                 ← Domain rules auto-loaded into Claude's context (glob-scoped) + agent-output-conventions.md (always-on house style)
├── skills/                ← Project-specific skills Claude writes as patterns emerge (starts empty)
├── workflows/             ← Dynamic multi-step scripts, become /<name> commands (starts empty — see workflows/README.md)
├── plans/                 ← Plan-mode output, one file per planned task
├── output-styles/         ← Response style presets (terse / explain)
├── errors.md              ← Major error log — Claude appends, you review
├── decisions.md           ← Architecture decision log — DocWriter maintains
├── bash.log               ← Audit trail of every bash command Claude ran (gitignored)
└── checkpoint.md          ← Mid-session state — Claude writes, next session reads

CLAUDE.local.md            ← Yours only. Gitignored. Personal notes, local context, machine-specific overrides Claude should know.
```

**You will interact with:**
- `settings.local.json` — your machine-specific settings
- `CLAUDE.md` — fill in Test/Lint/Build/Deploy commands as the project matures
- `rules/` — add domain rules as your area of the codebase grows
- `checkpoint.md` — automatically read at session start; written by `/checkpoint`

**You will not need to edit:**
- Hook scripts (unless you're adding custom behaviour)
- Agent definitions (unless you're creating new agents)
- `settings.json` directly (changes go through PR review)

---

## 6. Slash commands cheat sheet

| Command | What it does |
|---|---|
| `/plan` | Scaffold a structured plan before starting a task |
| `/checkpoint` | Save current session state (in-progress, next step, blockers) |
| `/commit` | Stage all → generate commit message from diff → push |
| `/pr` | Generate PR title + body → `gh pr create` |
| `/ship` | lint → build → test → `/commit` → `/pr` in one go |
| `/review` | Invoke CodeReviewer agent on the current diff |
| `/batch` | Split a large task into parallel subtasks (asks permission first) |
| `/verify` | Project-specific verification suite (fill this in per project) |
| `/handoff` | Write a surgical session transition doc before ending |
| `/caveman` | Cut response verbosity ~70% for long sessions |

---

## 7. Agents cheat sheet

Agents are isolated contexts — they get only what they need, nothing more. Always ask permission before spawning one.

| Agent | Use it when |
|---|---|
| `ReadOnly` | You want to explore code safely without any edit risk |
| `BuildValidator` | You want a clean build + test run and a pass/fail verdict |
| `LogAnalyzer` | You have crash logs, stack traces, or build errors to diagnose |
| `Researcher` | You need web-fetched information synthesised into a report |
| `CodeReviewer` | You want a structured diff review before merging |
| `DocWriter` | End of session — update decisions.md, errors.md, stale CLAUDE.md files |

---

## 8. The canary system

Every completed task ends with `[Canary:PROJECT_NAME:TASK_NAME]`.

- If Claude can't produce it, context has been dropped — it will say so and stop
- The `keep-going` hook checks for it when Claude tries to stop mid-task
- You'll see it at the bottom of Claude's response when a task is genuinely done

---

## 9. Hooks that run automatically

These are transparent by default — you don't invoke them, they just happen:

| Hook | When | What |
|---|---|---|
| `session-start` | Every session open | Surfaces in-progress checkpoint; sets tab title to git branch |
| `notify` | Claude goes idle or needs permission | Desktop notification so you don't watch the terminal |
| `log-bash` | Every bash command | Appends to `.claude/bash.log` — passive audit trail |
| `pre-deploy-guard` | Any deploy command | Runs lint + tests first; blocks if they fail |
| `privacy-guard` | Any `Read` or `Bash` referencing secret files | Blocks `.env*`, `*.pem`, `*.key`, SSH keys, `credentials.json` |
| `git-guard` | force-push, `reset --hard`, `git clean -f/-x`, `rm -rf` | Blocks with reason + safer next step (settings.json deny list also blocks these, this hook explains why) |
| `auto-format` | Every file write | Runs `PROJECT_FMT` on the file in the background |
| `keep-going` | Claude tries to stop | Checks for canary; nudges to continue if task is mid-flight |
| `statusline.sh` | Every render | Shows model, dir, git branch(dirty), context %, 5h/7d rate-limit usage |

---

## 10. Desktop notifications

The `notify` hook sends an OS notification when Claude needs your attention. It works automatically on macOS and Linux with a notification daemon. On WSL, it uses PowerShell.

If you're not getting notifications on Linux, install `libnotify`:
```bash
# Ubuntu/Debian
sudo apt install libnotify-bin

# Arch
sudo pacman -S libnotify
```

---

That's everything. Open Claude Code in the project root and start working.
