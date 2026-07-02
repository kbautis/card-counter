# Basic Strategy Trainer v2 — Live Table Simulation

## 1. Project overview

`card-counter` already has two trainers: a Hi-Lo speed-count trainer (untouched by
this build) and a Basic Strategy trainer that currently scores isolated hands
against one fixed chart (S17, DAS, no surrender). This build upgrades the Basic
Strategy trainer into a configurable, multi-hand live-table simulation: the
player sets real table rules (H17/S17, DAS on/off, number of simultaneous
hands), plays a full round the way a live table works (dealer peek, player
blackjacks, playable splits), can request a hint, and — in Live mode — tracks
the running/true count themselves and gets scored on Illustrious 18 index
deviations, not just base strategy. Learning goals: parameterized strategy-chart
design, multi-entity game-state machines, and building a scoring system that
separates "correct basic strategy" from "correct at this count" without
conflating the two.

## 2. Stack

- Backend: Flask (existing `app.py`), Python — match the version pinned in
  `.python-version` and dependencies already in `requirements.txt` / `pyproject.toml`
- Frontend: vanilla HTML/JS in `static/index.html` (existing pattern — no new
  framework)
- State: in-memory session dicts (existing `_STRATEGY_SESSIONS` pattern in `app.py`)
- Test framework: `pytest` (existing `tests/` suite, TDD — extend, don't replace)
- No database. No new external API integrations. No AI layer.
- Reference data source (not a live integration — verified once, embedded as
  static chart data): Blackjack Apprenticeship strategy charts, see Section 12
  Task 1 for exact source URLs and transcribed data.

## 3. Project structure

```
card-counter/
├── app.py                        # MODIFY: new/updated strategy routes (config, action, hint, stop)
├── card_engine.py                # UNCHANGED: reuse hi_lo_value/calculate_count/calculate_true_count
├── basic_strategy.py             # MODIFY: rules-parameterized chart lookup (H17/S17 × DAS/no-DAS)
├── strategy_engine.py            # MODIFY: multi-spot state machine, playable splits, live mode
├── deviations.py                 # NEW: Illustrious 18 index-play table + deviation lookup
├── requirements.txt
├── static/
│   └── index.html                # MODIFY: table config screen, multi-hand table UI, hint/stop
│                                  #         buttons, count entry (Live mode), summary screen
└── tests/
    ├── test_card_engine.py        # UNCHANGED
    ├── test_basic_strategy.py     # MODIFY: add H17/S17 × DAS/no-DAS cases
    ├── test_strategy_engine.py    # MODIFY: multi-spot, split-replay, dealer peek, naturals
    └── test_deviations.py         # NEW: Illustrious 18 lookup tests
```

## 4. Database schema

No database. Session state stays in-memory (existing `_STRATEGY_SESSIONS` dict,
TTL-purged), same rationale as the rest of the app: no persistence requirement,
avoids adding infra for a single-player local tool.

## 5. Skill pipeline

```
system-architect → software-engineer → fact-checker
"Design first"     "Build it right"    "Verify claims"
```

**Stage 1 — system-architect (before writing any code)**
Before implementing any task below, write a brief architecture note as a
comment at the top of the first file touched in that task: 5–10 lines on
service/function boundaries, data flow, and load-bearing decisions that must
not change (e.g. "DAS resolves pair Y/N at chart-lookup time, not as a
runtime downgrade — do not conflate with per-hand `can_split` legality").

**Stage 2 — software-engineer (while building)**
- Write the failing test first (RED), then implement (GREEN), then refactor (BLUE)
- Each function does one thing
- Fail fast — raise immediately on bad input, mirroring the existing
  `_validate_new_session_args` style in `strategy_engine.py`
- No secrets in code (n/a here — no new secrets), no print statements, no TODOs

**Stage 3 — fact-checker (before committing, and mandatory for Task 1)**
- All tests pass (`pytest` clean)
- Every chart cell in `basic_strategy.py` and `deviations.py` is checked
  against the transcribed source tables in Section 12 Task 1 — not assumed,
  not pattern-matched from memory of "how blackjack usually works"
- Code matches what the architecture note said it would do

## 6. Autonomous task loop instructions

When running headless, work through the task queue in order. For each task:

1. Read the full task checklist before starting anything
2. Architect — write the architecture note (Stage 1) before writing code
3. Build — implement using TDD: failing test → passing code → refactor
4. Verify — run pytest, check all boxes in the task checklist
5. Commit — git add -A && git commit -m "[Task N] <what was built>"
6. Update this file — check off completed boxes in the task checklist
7. Move to the next task immediately

Commit message format:
```
[Task 3] Multi-spot dealing — dealer peek, naturals, spot turn order, tests passing
[Task 4] Playable splits — split hands replay hit/stand/double to resolution
```

When to stop and wait for input:
- A chart cell in Section 12 Task 1's transcribed tables is ambiguous or
  contradicts itself (transcription may contain a typo — flag it, don't guess)
- An external API returns an unexpected response that changes the integration
  (n/a — no external APIs — but keep this rule for future-proofing)
- A task checklist item is ambiguous and two interpretations lead to different code

In all other cases: keep going.

## 7. Engineering principles

1. **Fail fast** — raise immediately on bad input, never return None silently
2. **Single responsibility** — each function does one thing; if you write "and"
   in a description, split the function
3. **Chart data over conditionals** — strategy/deviation logic should be table
   lookups (like the existing `_HARD_TOTALS` / `_SOFT_TOTALS` / `_PAIRS` dicts),
   not sprawling if/elif chains. This is the existing codebase's own pattern —
   follow it.
4. **TDD** — write a failing test before writing implementation; red → green → refactor
5. **No secrets in code** — n/a for this feature, but keep the rule live
6. **Clarity over cleverness** — name things what they are; `dealer_hits_soft17`
   not `h17`, `double_after_split` not `das`, in all new function signatures
   (short forms are fine in comments/docs, not in code identifiers)

## 8. Environment variables

None required for this feature. No new config beyond what's passed in API
request bodies (table rules, live-mode flag).

## 9. External integrations

None. The Blackjack Apprenticeship charts in Section 12 Task 1 are a
**verification reference**, not a live API — they're transcribed once into
static Python data structures and committed to the repo. Do not build a
scraper or a runtime fetch against blackjackapprenticeship.com.

## 10. AI layer

None.

## 11. Seed data

None.

## 12. Task queue

### Task 1 — Rules-parameterized strategy chart (H17/S17 × DAS/no-DAS)
- [ ] Rework `basic_strategy.py` so `correct_action()` takes two new required
      params: `dealer_hits_soft17: bool` and `double_after_split: bool`
- [ ] Maintain **two full hard/soft tables** (H17 and S17) — do not try to
      express one as a diff of the other; transcribe both in full from the
      source data below. This eliminates guesswork.
- [ ] The **pairs table is shared** between H17 and S17 (confirmed identical
      in both source PDFs) but has 5 cells whose value depends on
      `double_after_split`: 6,6v2 · 4,4v5 · 4,4v6 · 3,3v2 · 3,3v3 · 2,2v2 · 2,2v3
      marked `Y/N` in the source — resolve to `SPLIT` if `double_after_split`
      is `True`, otherwise resolve to whatever the *hard-total* chart says for
      that total (e.g. 4,4 = hard 8 = always `HIT`; 6,6 vs 2 = hard 12 vs 2 =
      `HIT`; 2,2/3,3 vs 2,3 = hard 4/6 = `HIT`). Do **not** reuse the existing
      `_downgrade()` function for this — that function handles runtime
      hand-state legality (e.g. "can't split again"), which is a different
      concept from a chart cell that depends on the table's ruleset. Keep
      these separate in the code and name them differently
      (e.g. `_resolve_das_pair_cell()` vs the existing `_downgrade()`).

**Source: H17 chart** (blackjackapprenticeship.com/wp-content/uploads/2024/09/H17-Basic-Strategy.pdf)
```
HARD TOTALS (rows = player total, cols = dealer upcard 2,3,4,5,6,7,8,9,10,A)
17: S S S S S S S S S S
16: S S S S S H H H H H
15: S S S S S H H H H H
14: S S S S S H H H H H
13: S S S S S H H H H H
12: H H S S S H H H H H
11: D D D D D D D D D D
10: D D D D D D D D H H
9:  H D D D D H H H H H
8:  H H H H H H H H H H
(≤8 default HIT if lower than shown, ≥17 default STAND — matches existing fallback logic)

SOFT TOTALS (A,2 .. A,9)
A,9(18… i.e. soft 20): S S S S S S S S S S
A,8(soft 19): S S S S Ds S S S S S
A,7(soft 18): Ds Ds Ds Ds Ds S S H H H
A,6(soft 17): H D D D D H H H H H
A,5(soft 16): H H D D D H H H H H
A,4(soft 15): H H D D D H H H H H
A,3(soft 14): H H H D D H H H H H
A,2(soft 13): H H H D D H H H H H
(D = double if allowed else hit; Ds = double if allowed else STAND — note Ds
falls back to STAND not HIT, this differs from the plain D fallback)
```

**Source: S17 chart** (blackjackapprenticeship.com/wp-content/uploads/2024/09/S17-Basic-Strategy.pdf)
```
HARD TOTALS
17: S S S S S S S S S S
16: S S S S S H H H H H
15: S S S S S H H H H H
14: S S S S S H H H H H
13: S S S S S H H H H H
12: H H S S S H H H H H
11: D D D D D D D D D H     <- differs from H17: 11 vs A is HIT not DOUBLE
10: D D D D D D D D H H
9:  H D D D D H H H H H
8:  H H H H H H H H H H

SOFT TOTALS
A,9(soft 20): S S S S S S S S S S
A,8(soft 19): S S S S S S S S S S   <- differs from H17: never doubles vs 6
A,7(soft 18): S Ds Ds Ds Ds S S H H H   <- differs from H17: vs2 is S not Ds
A,6(soft 17): H D D D D H H H H H
A,5(soft 16): H H D D D H H H H H
A,4(soft 15): H H D D D H H H H H
A,3(soft 14): H H H D D H H H H H
A,2(soft 13): H H H D D H H H H H
```

**Source: shared PAIRS table** (identical in both H17 and S17 PDFs)
```
A,A:   Y Y Y Y Y Y Y Y Y Y
10,10: N N N N N N N N N N
9,9:   Y Y Y Y Y N Y Y N N
8,8:   Y Y Y Y Y Y Y Y Y Y
7,7:   Y Y Y Y Y Y N N N N
6,6:   Y/N Y Y Y Y N N N N N
5,5:   N N N N N N N N N N
4,4:   N N N Y/N Y/N N N N N N
3,3:   Y/N Y/N Y Y Y Y N N N N
2,2:   Y/N Y/N Y Y Y Y N N N N
```
- [ ] `pytest tests/test_basic_strategy.py -v` — new tests cover at minimum:
      11 vs A under both rulesets (the clearest H17/S17 divergence), A,8 vs 6
      under both rulesets, and all 5 DAS-dependent pair cells under both
      `double_after_split=True` and `False`

### Task 2 — Table config API
- [ ] `POST /api/strategy/session` accepts: `num_decks` (1–8), `penetration`,
      `dealer_hits_soft17` (bool), `double_after_split` (bool), `num_hands`
      (simultaneous spots, validate 1–6 inclusive — 6 is the realistic cap for
      a full live table), `live_mode` (bool, default False)
- [ ] Drop the old `num_hands` = "total rounds to play" meaning entirely —
      replace with open-ended play (rounds continue until Stop or shoe
      exhaustion forces it). `num_hands` now means simultaneous spots per round.
- [ ] Validate all params fail-fast per existing `_validate_new_session_args` style
- [ ] `pytest` — config validation tests for each new param, including the
      1–6 `num_hands` boundary

### Task 3 — Multi-spot dealing, dealer peek, player naturals
- [ ] Each round deals `num_hands` independent spots plus one dealer hand
- [ ] If dealer up-card is Ace or 10: peek the hole card. If dealer has
      blackjack, reveal it immediately and resolve **every spot** with no
      player decisions offered (player blackjack on a spot = push against
      dealer blackjack; anything else = loss)
- [ ] If dealer does not have blackjack (or up-card wasn't A/10), check each
      spot for a player natural blackjack. Any spot with a natural
      auto-resolves as a win immediately — no hit/stand/double/split offered
      for that spot, even though the dealer hasn't played yet
- [ ] Remaining (non-blackjack) spots proceed to player decisions in spot
      order (spot 1, then spot 2, etc.)
- [ ] Dealer plays out **once per round**, after all spots have reached a
      terminal state, and resolves against each spot that's still live
      (standard live-table behavior — one dealer hand serves all spots)
- [ ] `pytest` — cover: dealer blackjack ends round with no decisions, player
      natural auto-resolves without offering actions, mixed round (one spot
      natural, one spot normal) resolves correctly, dealer plays once and
      settles all live spots

### Task 4 — Playable split hands
- [ ] When a spot's initial two cards are a pair and the player splits, that
      spot becomes two independently playable hands (each can hit/stand/double
      — no re-splitting; this is a deliberate simplification, same spirit as
      the current codebase's existing simplifications, and should be commented
      as such)
- [ ] Each split hand is scored against basic strategy independently as the
      player acts on it
- [ ] Dealer's single per-round hand resolves against both split hands
- [ ] `pytest` — split hand becomes two playable hands, hitting one doesn't
      affect the other, doubling on a split hand works, busting one split hand
      doesn't end the other

### Task 5 — Hint button
- [ ] New endpoint `POST /api/strategy/hint` — takes `session_id` and enough
      info to identify the active hand, returns the correct action **without**
      mutating game state, and flags that hand as "hint used"
- [ ] When the player's subsequent real action is applied via
      `/api/strategy/action`, the result includes `hint_used: bool`
- [ ] Accuracy scoring still counts hint-used decisions toward
      `correct_decisions`/`total_decisions` (confirmed with the user — hints
      count, just get tagged separately), but track a **separate**
      `hint_used_count` in session state for the summary
- [ ] `pytest` — hint doesn't mutate state, hint-used decisions still score
      normally, hint count accumulates correctly

### Task 6 — Live mode: true count + Illustrious 18 deviations
- [ ] New file `deviations.py` — table of index plays keyed by
      `(hand_description, dealer_upcard)` → `{threshold, direction, deviate_to}`,
      transcribed from the source below. `direction` is `'+'` (deviate at or
      above threshold) or `'-'` (deviate at or below threshold)

**Source: S17 Illustrious 18 deviation chart** (blackjackapprenticeship.com/wp-content/uploads/2019/07/BJA_S17.pdf)
```
Insurance: TAKE at true count 3+

Pairs (index shown only where it differs from the S17 base chart):
10,10 vs 4: split at 6+     10,10 vs 5: split at 5+     10,10 vs 6: split at 4+

Soft totals:
A,8 vs 4: double at 3+   A,8 vs 5: double at 1+   A,8 vs 6: double at 1+
A,6 vs 2: double at 1+

Hard totals:
16 vs 9: stand at 4+     16 vs 10: stand at 0+ (0 or above)
15 vs 10: stand at 4+
13 vs 2: hit at -1 or below
12 vs 2: stand at 3+      12 vs 3: stand at 2+      12 vs 4: hit at 0 or below
11 vs A: double at 1+
10 vs 9: double at 3+     10 vs 10: double at 4+    10 vs A: double at 4+
9 vs 2: double at 1+      9 vs 7: double at 3+
8 vs 6: double at 2+
```
This chart is the assumed reference for Live mode regardless of the table's
H17/S17 config — flag this explicitly in the UI ("deviations shown are for a
standard S17 game; exact indices shift slightly under H17") rather than
silently applying S17 indices to an H17 table. Building H17-specific
deviations is out of scope for this pass (see Stretch Features).

- [ ] Reuse `card_engine.hi_lo_value()` / `calculate_count()` /
      `calculate_true_count()` for the running/true count — do not duplicate
      this logic in `strategy_engine.py` or `deviations.py`
- [ ] Session tracks running count internally at all times once `live_mode`
      is True (increment as cards are dealt/drawn — dealer hole card only
      counts once revealed, matching real-table counting practice)
- [ ] New field on the hand view: when `live_mode` is True, the client can
      request the current true count on demand (a "check count" action) —
      it is not pushed automatically, matching the brief's "if they want to" framing
- [ ] For each decision made in `live_mode`, check `deviations.py` for a
      matching entry. If one exists, compute whether the deviation-correct
      play differs from the true count at decision time, and score
      `deviation_correct`/`deviation_total` **separately** from base
      `correct_decisions`/`total_decisions` — a deviation decision should
      not double-count against base strategy accuracy
- [ ] `pytest` — true count reused correctly from `card_engine`, deviation
      lookup returns correct threshold comparisons for both `+` and `-`
      directions, deviation scoring is tracked separately from base accuracy

### Task 7 — Stop button + end-of-session summary
- [ ] New endpoint `POST /api/strategy/stop` — takes `session_id`, ends the
      session immediately (mid-shoe, mid-round is fine — just stop cleanly,
      don't force the current round to finish), deletes it from
      `_STRATEGY_SESSIONS`, and returns a summary payload
- [ ] Natural end of session (if you choose to keep any session-length cap —
      otherwise sessions only end via Stop or shoe exhaustion after many
      reshuffles, either is fine) returns the **same summary shape**
- [ ] Summary payload includes: hands played, wins/losses/pushes, basic
      strategy accuracy % (`correct_decisions / total_decisions`), hint-used
      count, and — only if `live_mode` was on — deviation accuracy %
      (`deviation_correct / deviation_total`) reported separately from base
      accuracy
- [ ] `pytest` — stop mid-round returns a valid summary, summary math is
      correct against known fixture state, live-mode-off sessions omit the
      deviation accuracy field entirely (not just zero it out)

### Task 8 — Frontend (`static/index.html`)
- [ ] Table config screen: decks, penetration, H17/S17 toggle, DAS toggle,
      number of simultaneous hands (1–6), Live mode toggle
- [ ] Multi-hand table view: all active spots visible, clear indicator of
      which spot/hand is currently awaiting a decision, dealer up-card (and
      hole card once revealed) visible to all
- [ ] Hint button on the active hand
- [ ] Stop button always visible during play
- [ ] Live mode: a "check my count" control that reveals running/true count
      on demand, not automatically
- [ ] Summary screen on session end: same fields as the Task 7 payload,
      rendered clearly (accuracy % prominent, deviation accuracy shown
      separately and only when Live mode was used)
- [ ] Manual verification: run the app, play at least one full round with 3+
      simultaneous hands including a split, confirm dealer peek and player
      blackjack auto-resolve visually, confirm Stop produces a summary

### Task 9 — Full regression pass
- [ ] `python -m pytest tests/ -v` — entire suite green, including untouched
      Count Trainer tests (confirm no regression)
- [ ] Fact-checker pass specifically on `basic_strategy.py` and
      `deviations.py` — every transcribed chart cell checked against Section
      12 Task 1 and this task's source block, not against memory or
      assumption

## 13. Definition of done

- [ ] All tasks above checked off
- [ ] All rule combinations (S17/H17 × DAS/no-DAS) produce strategy-correct
      answers matching the transcribed source charts
- [ ] Split hands are fully playable through to resolution
- [ ] Dealer peek and player-natural auto-resolve both work without offering
      illegal decisions
- [ ] Hint button works and is tracked separately without altering scored accuracy
- [ ] Live mode correctly separates deviation accuracy from base strategy accuracy
- [ ] Stop button and natural session end both produce the same summary shape
- [ ] All tests passing
- [ ] Written retrospective completed

## 14. Stretch features (only after definition of done is met)

- H17-specific deviation index chart (currently only S17 indices are implemented)
- Late surrender option (both basic strategy and its own deviation indices)
- Insurance as an explicit playable decision (currently only referenced by
  the deviation table, not offered as a real action)
- Re-splitting (currently capped at one split per spot)
- Bankroll/betting simulation layered on top of Live mode bet-sizing by count

## 15. Independence checks

- Can you explain, from scratch, why DAS changes 5 specific pair cells but
  H17/S17 changes different cells entirely, without looking at the source tables?
- Can you explain why deviation scoring must be tracked separately from base
  strategy accuracy rather than folded into the same counter?
- Can you walk through the full round order (peek → naturals → spot decisions
  → single dealer play → resolve all spots) from memory?
- Can you explain why a Y/N pair-split chart cell is resolved at
  chart-lookup time based on the table ruleset, rather than via the existing
  `_downgrade()` runtime-legality function?