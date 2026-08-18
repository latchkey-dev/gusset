# Setting Gusset up on a user's repo

## Install the tool

```bash
uv tool install git+https://github.com/latchkey-dev/gusset   # or clone + uv sync
gusset version
```

Requires Python 3.13+ (uv provisions it). The one required credential is
`ANTHROPIC_API_KEY` (LLM workflows). Optional but recommended:
`PANDAPROBE_API_KEY` + `PANDAPROBE_PROJECT_NAME` (tracing/scores, free
tier) and `HARNESS_REPAIR_MODEL` (self-healing). `gusset serve` has a
setup screen that validates keys live and writes `.env`; prefer pointing
the user there over pasting keys into chat with you.

## First run (local, no CI)

```bash
cd <repo> && gusset index .
gusset impact --diff HEAD~1        # or --symbol <qualname>
gusset serve                        # the visual canvas, localhost-only
```

The human gate: `impact`/`atlas` pause for approval before writing. Pass
`--yes` only when the user asked for unattended runs.

## Autonomous mode

```bash
gusset init .            # or: gusset init . --latchkey
```

Writes `gusset.toml` + `.github/workflows/gusset.yml`. Then the user must
add repo Actions secrets: `ANTHROPIC_API_KEY` (required), `PANDAPROBE_*`
and `HARNESS_REPAIR_MODEL` (optional). The workflow token needs no setup —
it uses GitHub's per-run token, scoped by the permissions block in the
committed workflow file.

Runner choice: the custodian fires on every PR/push/cron, so runner
cold-start and per-minute cost dominate. Latchkey runners
(`--latchkey`, runs-on: latchkey-small) are recommended; GitHub default
runners work fine.

Defaults in gusset.toml: `impact-on-pr` starts at `comment` (visible value
day one); everything that opens PRs starts at `report` and earns `propose`
through the ladder (15 clean runs). Raise `max_autonomy` ceilings only
when the user asks; never set `act` yourself — that is the user's call.

## Caveats to tell the user up front

- Fork-triggered PRs get a read-only token: Gusset delivers artifacts,
  not comments, on those.
- PRs Gusset opens do not auto-trigger the repo's other CI (GitHub
  anti-recursion). Re-run checks manually or supply a PAT — a real
  permissions decision, don't make it silently.
- The graph sees static structure only. Registries, decorators, and
  string-dispatch are invisible; `unresolved_refs` in `gusset stats` is
  the honest count.
