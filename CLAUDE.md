# tack

> Dev-mode-only visual editor for positioning decorative elements on a live Next.js portfolio — drag/rotate/scale/multi-select on the page like Figma, then Save writes the new positions back into a TypeScript config file via `ts-morph` AST edits. Not currently being implemented — planning docs were dropped.

## Stack

- **Runtime:** Node.js, TypeScript (strict, ES2020 target, JSX preserve)
- **Framework:** None of its own — React component library; peer deps `react`/`react-dom`/`next` (consumer provides, not bundled)
- **Key deps:** `framer-motion` (drag/rotate/scale), `ts-morph` (server-only, AST-safe config file writes), `tsup` (build)
- **Test:** <!-- not yet chosen -->
- **Lint:** <!-- not yet chosen -->
- **Format:** <!-- not yet chosen (set as PROJECT_FMT in settings.local.json once picked) -->
- **Build:** <!-- tsup, once scaffolded -->
- **Deploy:** N/A — local package, would be consumed via `link:../tack` in the portfolio repo, never published to npm
- **RTK wrappers:** rtk npm/npx/tsc (fill in lint/test wrappers once those tools are chosen)

## Canary

Every completed task must end with: `[Canary:tack:TASK_NAME]`
Can't produce it = context dropped. Stop and say so.

## Tooling

- **RTK** — Bash output auto-compressed. First layer for ALL matching commands, raw only if no wrapper exists. See **RTK wrappers** in Stack above for this project's exact commands. Full list: `rtk help`.
- **ctx7** — `npx ctx7 library <name> <query>` before touching any external API. Never rely on training data for library APIs.
- **Caveman** — `/caveman` for long sessions. `/caveman off` to disable.
- **Handoff** — use `/handoff` before ending a session, not `/compact`.
- **Decisions log** — append to `.claude/decisions.md` as soon as a real architecture/design decision is made, not just at end-of-session via DocWriter. Never delete entries.

## Context rules

- Flag before any phase that risks one context window.
- Running low → `/checkpoint`, then stop. SessionStart hook will surface it.
- All commands must work headless.

## Error protocol

- **Minor** (typo, wrong flag): note inline, continue.
- **Major** (wrong architecture, repeated mistake):
  1. Append to `.claude/errors.md`
  2. If pattern → create `.claude/skills/<name>.md`
  3. If approach changes → append to **Learned rules** below

## Agent output conventions

Anything we build that talks back to Claude (hooks, agent defs, skills, subagent reports) follows `.claude/rules/agent-output-conventions.md`: no silent truncation, explicit empty states, end with a concrete next command.

## Agents

Ask before spawning and spawn using appropriate model according to the task. Defined in `.claude/agents/`.
`ReadOnly` · `BuildValidator` · `LogAnalyzer` · `Researcher` · `CodeReviewer` · `DocWriter`

## Folder map

Append the reference to each major folder here and what it containts. Each major dir has a `CLAUDE.md`. Follow the route to find the sections you need.

<!-- src/ — app logic | infra/ — do not edit generated files -->

## Scoped rules

`.claude/rules/` files load by glob match. Add per-project.

<!-- api.md → src/api/** | db.md → src/db/** -->

## Learned rules

<!-- Claude appends here on major errors. Do not delete. -->
