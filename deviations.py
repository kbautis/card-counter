"""
deviations.py — Illustrious 18 index-play lookup for the Live-mode trainer.

Architecture note (system-architect, Task 6):
  - This module is a pure data/lookup layer, same "chart data over
    conditionals" pattern as basic_strategy.py — no game-state mutation,
    no count tracking (that stays in card_engine/strategy_engine).
  - Keyed by (hand_description, dealer_upcard_column) so a deviation is a
    single dict lookup, not an if/elif chain. `hand_description` mirrors
    the same pair/soft/hard classification basic_strategy.py uses, so a
    deviation entry and its base-strategy chart cell describe the same hand.
  - Deviations are the S17 Illustrious 18 index chart specifically. Callers
    (strategy_engine) apply it regardless of the table's own H17/S17
    config — flagged explicitly to the player in the UI, not silently
    treated as exact — because building a separate H17 deviation chart is
    out of scope for this pass (see CLAUDE.md Stretch Features).
  - `direction` is '+' (deviate when true_count >= threshold) or '-'
    (deviate when true_count <= threshold), matching how index plays are
    conventionally written ("stand at 4+", "hit at -1 or below").
"""
from basic_strategy import HIT, STAND, DOUBLE, SPLIT, hand_total, is_pair

# Insurance isn't wired up as a playable decision (see CLAUDE.md Stretch
# Features) — this threshold is reference data only.
INSURANCE_TRUE_COUNT_THRESHOLD = 3

# Keyed by (hand_description, dealer_upcard_column). See hand_description().
DEVIATIONS = {
    ('pair-10', '4'):  {'direction': '+', 'threshold': 6, 'deviate_to': SPLIT},
    ('pair-10', '5'):  {'direction': '+', 'threshold': 5, 'deviate_to': SPLIT},
    ('pair-10', '6'):  {'direction': '+', 'threshold': 4, 'deviate_to': SPLIT},

    ('soft-19', '4'):  {'direction': '+', 'threshold': 3, 'deviate_to': DOUBLE},  # A,8 vs 4
    ('soft-19', '5'):  {'direction': '+', 'threshold': 1, 'deviate_to': DOUBLE},  # A,8 vs 5
    ('soft-19', '6'):  {'direction': '+', 'threshold': 1, 'deviate_to': DOUBLE},  # A,8 vs 6
    ('soft-17', '2'):  {'direction': '+', 'threshold': 1, 'deviate_to': DOUBLE},  # A,6 vs 2

    ('hard-16', '9'):  {'direction': '+', 'threshold': 4, 'deviate_to': STAND},
    ('hard-16', '10'): {'direction': '+', 'threshold': 0, 'deviate_to': STAND},
    ('hard-15', '10'): {'direction': '+', 'threshold': 4, 'deviate_to': STAND},
    ('hard-13', '2'):  {'direction': '-', 'threshold': -1, 'deviate_to': HIT},
    ('hard-12', '2'):  {'direction': '+', 'threshold': 3, 'deviate_to': STAND},
    ('hard-12', '3'):  {'direction': '+', 'threshold': 2, 'deviate_to': STAND},
    ('hard-12', '4'):  {'direction': '-', 'threshold': 0, 'deviate_to': HIT},
    ('hard-11', 'A'):  {'direction': '+', 'threshold': 1, 'deviate_to': DOUBLE},
    ('hard-10', '9'):  {'direction': '+', 'threshold': 3, 'deviate_to': DOUBLE},
    ('hard-10', '10'): {'direction': '+', 'threshold': 4, 'deviate_to': DOUBLE},
    ('hard-10', 'A'):  {'direction': '+', 'threshold': 4, 'deviate_to': DOUBLE},
    ('hard-9', '2'):   {'direction': '+', 'threshold': 1, 'deviate_to': DOUBLE},
    ('hard-9', '7'):   {'direction': '+', 'threshold': 3, 'deviate_to': DOUBLE},
    ('hard-8', '6'):   {'direction': '+', 'threshold': 2, 'deviate_to': DOUBLE},
}


def hand_description(player_ranks: list[str], can_split: bool) -> str:
    """
    Classify a hand the same way the deviation table is keyed:
    'pair-<rank>' (only when splitting is currently legal), else
    'soft-<total>' or 'hard-<total>'.
    """
    if can_split and is_pair(player_ranks):
        pair_rank = '10' if player_ranks[0] in ('10', 'J', 'Q', 'K') else player_ranks[0]
        return f'pair-{pair_rank}'
    total, soft = hand_total(player_ranks)
    kind = 'soft' if soft else 'hard'
    return f'{kind}-{total}'


def deviation_lookup(description: str, dealer_upcard_column: str) -> dict | None:
    """Return the deviation entry for this hand/upcard, or None if there isn't one."""
    return DEVIATIONS.get((description, dealer_upcard_column))


def deviation_triggered(entry: dict, true_count: float) -> bool:
    """Whether the true count crosses this deviation's threshold in its direction."""
    if entry is None:
        raise ValueError("deviation_triggered requires a deviation entry")
    if entry['direction'] == '+':
        return true_count >= entry['threshold']
    if entry['direction'] == '-':
        return true_count <= entry['threshold']
    raise ValueError(f"Unknown deviation direction: {entry['direction']!r}")
