# Evidence: vercel/next.js (public issue tracker, history since 2026-07-01)

Generated 2026-10-12T07:31:36Z by `tacit backfill-github`. Brain: anthropic (claude-opus-5); judge: separate model.

| | |
|---|---|
| Events ingested | 9569 (bots excluded) |
| Threads | 5878 |
| Humans observed | 2800 |
| Playbooks mined | 28 |
| Backtested | 8 playbooks with ≥7 examples, 142 real triggers |
| Would have handled (judge ≥ 0.5) | 47 / 142 = 33% |

Caveat: the Anthropic API budget ran out during the last job (memory regressions). 18 of its 25 drafts fell back to the
deterministic local brain and overlap scoring (`graded_by: overlap`); the 7 model-judged drafts in that job all scored 0.
Every other number on this page is a Claude draft graded by the separate judge model. Excluding that job: 47 / 117 = 40%.

## Per job

| Job | Owner | Examples | Handled | Mean judge score |
|---|---|---|---|---|
| Lock stale closed issues | brynary | 14 | 13/13 (100%) | 1.00 |
| Claim open bug issues for a PR | LeonxLJX | 17 | 8/8 (100%) | 0.99 |
| Close unsigned fix PRs for signed replacements | marcoshernanz | 7 | 8/19 (42%) | 0.49 |
| Answer docs requests with existing docs | marcoshernanz | 23 | 8/25 (32%) | 0.47 |
| Verify repro and close with findings | marcoshernanz | 1174 | 5/25 (20%) | 0.35 |
| Triage and close long-running issue threads | marcoshernanz | 14 | 5/25 (20%) | 0.35 |
| Review Turbopack PRs with line-level fixes | sokra | 13 | 0/2 (0%) | 0.05 |
| Benchmark and report memory regressions | xabierlameiro | 7 | 0/25 (0%) | 0.22 |

## What the judge caught

Lowest-scored drafts and the judge's reason. These are the drafts the trust ladder would never promote.

**Review Turbopack PRs with line-level fixes** — judge 0.05: _The assistant points to a different file/line and suggests adding a new method, whereas sokra actually said the specific code block should be removed entirely as redundant._

> draft: https://github.com/vercel/next.js/blob/ef97e5ace5ab7451748ae474b9e68be5f63ada32/turbopack/crates/turbo-tasks-fs/src/invalidator_map.rs#L62-L70

Add a `contains_path` method here that only takes the read lock instead of e
>
> human: https://github.com/vercel/next.js/blob/ef97e5ace5ab7451748ae474b9e68be5f63ada32/turbopack/crates/turbo-tasks-fs/src/watcher/mod.rs#L675-L681

This isn't needed and should be removed. The batch will flush when the schedul

**Review Turbopack PRs with line-level fixes** — judge 0.05: _The draft invents an unrelated per-shard locking suggestion instead of sokra's actual question about avoiding reading snapshot_mode._

> draft: https://github.com/vercel/next.js/blob/8f98fd149a76ea575ac37c8b6766ad543f5df425/turbopack/crates/turbo-tasks-backend/src/backend/storage.rs#L982

Don't scan all shards under the exclusion. Take the exclusion per shard, m
>
> human: https://github.com/vercel/next.js/blob/8f98fd149a76ea575ac37c8b6766ad543f5df425/turbopack/crates/turbo-tasks-backend/src/backend/storage.rs#L982

Can we avoid reading snapshot_mode here?

**Verify repro and close with findings** — judge 0.05: _Draft closes as 'expected behavior' with a different explanation, contradicting the actual fix citation (PR #37815) that resolved it as a bug fix._

> draft: Thanks for the report. I retested the reproduction on current Next.js and this is expected behavior for automatically statically optimized pages. Those pages are prerendered without the query, so the router performs a sh
>
> human: Thanks for reporting this. This was fixed in Next.js 12.2.0 by #37815, which prevents hydration-only query updates from emitting route change events. I verified the original reproduction on current stable and canary: dir

**Close unsigned fix PRs for signed replacements** — judge 0.05: _Draft cites a different PR number and rationale (signed commit) instead of the actual superseding PR #68947 with regression coverage._

> draft: Closing in favor of #97142, which carries the same change in a signed commit while preserving the original authorship and attribution. Thank you for the contribution!
>
> human: Thanks for working on this! This issue was addressed by #68947, which also added regression coverage, so we’re closing this PR as superseded.

**Close unsigned fix PRs for signed replacements** — judge 0.05: _Draft cites a different replacement PR (#97712) and different rationale (signed commit) than the actual #96008 with comprehensive fix/tests, factually incorrect._

> draft: Closing in favor of #97712, which carries the same change in a signed commit while preserving the original authorship and attribution. Thank you for the contribution!
>
> human: Thanks for the fix. This has since been addressed more comprehensively by #96008, including byte-exact handling and regression tests for binary bodies. Closing as superseded.

**Close unsigned fix PRs for signed replacements** — judge 0.05: _Draft gives a fabricated reason (superseding PR #97712) instead of the actual reason that the component was removed in #78913, misrepresenting the closure rationale._

> draft: Closing in favor of #97712, which carries the same change in a signed commit while preserving the original authorship and attribution. Thank you for the contribution!
>
> human: Thanks for catching this! The Supabase auth UI has since been replaced in #78913, which removed this component, so the change no longer applies. Closing as superseded.

## What it got right

**Claim open bug issues for a PR** — judge 0.95: _Same claim intent and attribution, with harmless added detail and truncated title text._

> draft: I'd like to take this one (`Misleading "next-head-count is missing" error for invalid he`). I'll look into the root cause and follow up with a PR. (claiming via @LeonxLJX)
>
> human: I'd like to take this one — I'll follow up with a PR. (claiming via @LeonxLJX)

**Claim open bug issues for a PR** — judge 0.95: _Same claim intent and PR commitment, just includes extra title quoting and minor phrasing additions._

> draft: I'd like to take this one (`` `@next/next/no-html-link-for-pages` rule does not work with ``). I'll look into the root cause and follow up with a PR. (claiming via @LeonxLJX)
>
> human: I'd like to take this one — I'll follow up with a PR. (claiming via @LeonxLJX)

**Close unsigned fix PRs for signed replacements** — judge 0.95: _Only difference is omitting the explicit @mention of the original author's name, substance unchanged._

> draft: Closing in favor of #97136, which carries the same changes in a signed commit while preserving the original authorship and attribution. Thank you for the contribution!
>
> human: Closing in favor of #97136, which carries the same changes in a signed commit while preserving @adityagiri3600’s original authorship and attribution. Thank you for the contribution!

**Answer docs requests with existing docs** — judge 0.95: _Conveys same technical explanation and resolution via transpilePackages, just adds doc links not present in original._

> draft: Thanks for raising this. Next.js determines scoping by filename convention, so only `*.module.css` is treated as a CSS Module — a file named `styles.scoped.css` is still global CSS as far as the compiler is concerned, wh
>
> human: Thanks for the report. The Pages Router determines CSS behavior from the `.module.css` filename convention and cannot infer that `.scoped.css` has already been scoped. The supported path for a dependency that imports its

