# What is Gusset, plainly

## The problem

Three questions every team keeps paying for, over and over:

1. **"If I change this, what breaks?"** — answered today by grep, tribal
   knowledge, and hope.
2. **"How does this codebase fit together?"** — answered by an
   architecture doc that was true eight months ago.
3. **"Can I trust what an AI says about my code?"** — usually no: ask a
   model what your change affects and it answers fluently, confidently,
   and unverifiably.

## The idea

Gusset keeps a **map of provable facts** about your repo: every function,
class, and package, and every call, import, and inheritance between them
— parsed from the code, never guessed. That map does two jobs at once:

- It's the **map** the AI workflows navigate (so they don't explore blind).
- It's the **fact-checker** for everything they say. When a workflow
  claims "changing `make_model` affects `cli.impact`," that edge either
  exists in the map or the claim is **dropped and logged** before you
  ever see it.

That's the whole trick: *the interesting claims about code are checkable,
so Gusset checks every one.* The AI writes the explanations; the map
decides the facts.

## What you actually get

| You do | Gusset does |
|---|---|
| Open a PR | Comments the verified blast radius — what your change affects, with the picture, each line carrying its proof |
| Merge to main | Opens a PR refreshing the architecture doc when structure actually shifted |
| Nothing (weekly cron) | Reports dead code with per-symbol proof; flags doc references that no longer resolve |
| `gusset serve` | A local canvas: the map itself, replays of every run, and the trust ledger |

## Why you can leave it unattended

Every run is scored deterministically against the map (did it find
everything reachable? did every named symbol exist?). Those scores feed an
**autonomy ladder**: each job starts only allowed to write files, earns
the right to comment and then to open PRs through sustained clean runs,
and is demoted automatically when quality slips. The top rung (merging
anything itself) can only ever be granted by a human, in a config file.
The whole ledger is committed to your repo — every promotion and demotion,
with its reason.

## How people use it

- **Directly**: review the PRs and comments it produces. That's it — the
  human gate *is* code review, which your team already does.
- **Through your AI tool**: Gusset ships an agent skill, so Claude Code /
  Cursor / etc. run it for you — "what does my change affect?" makes your
  agent call `gusset impact` and use the *verified* list as its own
  editing checklist, instead of guessing.
- **Locally**: `gusset serve` for the visual canvas; the CLI for scripts
  and CI.

## What it is not

Not an IDE context plugin (that space is served), not a code reviewer of
style/logic (it reasons about *structure*), not magic on dynamic code
(registries and string-dispatch are invisible to static parsing — it
tells you what it can't see rather than guessing: the unresolved count is
printed on every index).
