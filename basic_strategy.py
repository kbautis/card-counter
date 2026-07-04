"""
basic_strategy.py — Rules-parameterized basic strategy chart lookup.

Architecture note (system-architect, Task 1):
  - `correct_action()` takes the table's ruleset (`dealer_hits_soft17`,
    `double_after_split`) as required params rather than baking in one
    fixed ruleset — the trainer now supports live per-session table config.
  - Two FULL hard/soft tables are kept (H17, S17), transcribed independently
    from source rather than expressed as a diff of one another, to avoid
    silently propagating a transcription error across rulesets.
  - The pairs table is shared between rulesets (confirmed identical in both
    source charts) but 5 cells are DAS-dependent. That resolution
    (`_resolve_das_pair_cell`) is a *chart-lookup-time* decision driven by
    the table's ruleset, and is kept completely separate from `_downgrade`,
    which handles *runtime hand-state legality* (e.g. "can't double after a
    hit", "can't re-split"). These are different concepts — one asks "what
    does this table's rules say the chart cell resolves to", the other asks
    "is the chart's answer legal to actually perform right now" — and
    conflating them would make both harder to verify against source data.
  - `Ds` is an internal marker (soft-total cells only) meaning "double if
    allowed, otherwise STAND" — distinct from plain `D`, which falls back to
    HIT when double isn't allowed. `_downgrade` resolves both.

All functions are pure and side-effect free. Preconditions fail fast.
"""

RANKS_ORDER = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

HIT, STAND, DOUBLE, SPLIT = 'H', 'S', 'D', 'P'

# Internal-only markers — never returned from correct_action().
_DS = 'Ds'          # soft-total: double if allowed, else STAND (not HIT)
_COND_SPLIT = 'Y/N'  # pair cell: split if double_after_split else hard-total fallback
_NO_SPLIT = 'N'      # pair cell: never split, always hard-total fallback

_ACTION_NAMES = {HIT: 'Hit', STAND: 'Stand', DOUBLE: 'Double', SPLIT: 'Split'}


def action_name(action: str) -> str:
    """Return the human-readable name for an action code."""
    if action not in _ACTION_NAMES:
        raise ValueError(f"Unknown action code: {action!r}")
    return _ACTION_NAMES[action]


def _rank_value(rank: str) -> int:
    """Blackjack value of a rank, treating Ace as 11 (soft) for total math."""
    if rank == 'A':
        return 11
    if rank in ('10', 'J', 'Q', 'K'):
        return 10
    return int(rank)


def upcard_key(dealer_upcard_rank: str) -> str:
    """Normalise a dealer up-card rank to a chart column key (2-9, 10, A)."""
    if dealer_upcard_rank in ('10', 'J', 'Q', 'K'):
        return '10'
    return dealer_upcard_rank


def hand_total(ranks: list[str]) -> tuple[int, bool]:
    """
    Return (total, is_soft) for a list of card ranks.

    is_soft is True when an Ace is being counted as 11 without busting.
    """
    if not ranks:
        raise ValueError("hand_total requires at least one card")

    total = sum(_rank_value(r) for r in ranks)
    num_aces = ranks.count('A')

    # Downgrade aces from 11 to 1 (i.e. subtract 10) until we don't bust.
    soft = num_aces > 0
    while total > 21 and num_aces > 0:
        total -= 10
        num_aces -= 1
        if num_aces == 0:
            soft = False

    return total, soft


def is_pair(ranks: list[str]) -> bool:
    """True when a two-card hand is a pair for splitting purposes (rank-value based)."""
    if len(ranks) != 2:
        return False
    return _rank_value(ranks[0]) == _rank_value(ranks[1])


# ── Chart data ────────────────────────────────────────────────────────────────
# Each table maps a row key -> dict of dealer-upcard-column -> action/marker.
# Columns always present: 2,3,4,5,6,7,8,9,10,A
# Rows 8-17 explicit for hard totals (below 8 = always HIT, 17+ = always
# STAND — same default-fallback convention as the original single-table code).

_HARD_TOTALS_H17 = {
    8:  {'2': HIT, '3': HIT, '4': HIT, '5': HIT, '6': HIT, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    9:  {'2': HIT, '3': DOUBLE, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    10: {'2': DOUBLE, '3': DOUBLE, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': DOUBLE, '8': DOUBLE, '9': DOUBLE, '10': HIT, 'A': HIT},
    11: {'2': DOUBLE, '3': DOUBLE, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': DOUBLE, '8': DOUBLE, '9': DOUBLE, '10': DOUBLE, 'A': DOUBLE},
    12: {'2': HIT, '3': HIT, '4': STAND, '5': STAND, '6': STAND, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    13: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': STAND, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    14: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': STAND, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    15: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': STAND, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    16: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': STAND, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    17: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': STAND, '7': STAND, '8': STAND, '9': STAND, '10': STAND, 'A': STAND},
}

_HARD_TOTALS_S17 = {
    8:  {'2': HIT, '3': HIT, '4': HIT, '5': HIT, '6': HIT, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    9:  {'2': HIT, '3': DOUBLE, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    10: {'2': DOUBLE, '3': DOUBLE, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': DOUBLE, '8': DOUBLE, '9': DOUBLE, '10': HIT, 'A': HIT},
    11: {'2': DOUBLE, '3': DOUBLE, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': DOUBLE, '8': DOUBLE, '9': DOUBLE, '10': DOUBLE, 'A': HIT},
    12: {'2': HIT, '3': HIT, '4': STAND, '5': STAND, '6': STAND, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    13: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': STAND, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    14: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': STAND, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    15: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': STAND, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    16: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': STAND, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    17: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': STAND, '7': STAND, '8': STAND, '9': STAND, '10': STAND, 'A': STAND},
}

# Rows keyed by soft total: 13 = A,2 ... 20 = A,9. Soft 21 is never a decision point.
_SOFT_TOTALS_H17 = {
    13: {'2': HIT, '3': HIT, '4': HIT, '5': DOUBLE, '6': DOUBLE, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    14: {'2': HIT, '3': HIT, '4': HIT, '5': DOUBLE, '6': DOUBLE, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    15: {'2': HIT, '3': HIT, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    16: {'2': HIT, '3': HIT, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    17: {'2': HIT, '3': DOUBLE, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    18: {'2': _DS, '3': _DS, '4': _DS, '5': _DS, '6': _DS, '7': STAND, '8': STAND, '9': HIT, '10': HIT, 'A': HIT},
    19: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': _DS, '7': STAND, '8': STAND, '9': STAND, '10': STAND, 'A': STAND},
    20: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': STAND, '7': STAND, '8': STAND, '9': STAND, '10': STAND, 'A': STAND},
}

_SOFT_TOTALS_S17 = {
    13: {'2': HIT, '3': HIT, '4': HIT, '5': DOUBLE, '6': DOUBLE, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    14: {'2': HIT, '3': HIT, '4': HIT, '5': DOUBLE, '6': DOUBLE, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    15: {'2': HIT, '3': HIT, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    16: {'2': HIT, '3': HIT, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    17: {'2': HIT, '3': DOUBLE, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    18: {'2': STAND, '3': _DS, '4': _DS, '5': _DS, '6': _DS, '7': STAND, '8': STAND, '9': HIT, '10': HIT, 'A': HIT},
    19: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': STAND, '7': STAND, '8': STAND, '9': STAND, '10': STAND, 'A': STAND},
    20: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': STAND, '7': STAND, '8': STAND, '9': STAND, '10': STAND, 'A': STAND},
}

# Shared between H17 and S17 (confirmed identical in both source PDFs).
# SPLIT = always split. _COND_SPLIT = split only if double_after_split,
# else fall back to the hard-total chart. _NO_SPLIT = never split, always
# fall back to the hard-total chart (see _resolve_das_pair_cell).
_PAIRS = {
    'A':  {'2': SPLIT, '3': SPLIT, '4': SPLIT, '5': SPLIT, '6': SPLIT, '7': SPLIT, '8': SPLIT, '9': SPLIT, '10': SPLIT, 'A': SPLIT},
    '10': {'2': _NO_SPLIT, '3': _NO_SPLIT, '4': _NO_SPLIT, '5': _NO_SPLIT, '6': _NO_SPLIT, '7': _NO_SPLIT, '8': _NO_SPLIT, '9': _NO_SPLIT, '10': _NO_SPLIT, 'A': _NO_SPLIT},
    '9':  {'2': SPLIT, '3': SPLIT, '4': SPLIT, '5': SPLIT, '6': SPLIT, '7': _NO_SPLIT, '8': SPLIT, '9': SPLIT, '10': _NO_SPLIT, 'A': _NO_SPLIT},
    '8':  {'2': SPLIT, '3': SPLIT, '4': SPLIT, '5': SPLIT, '6': SPLIT, '7': SPLIT, '8': SPLIT, '9': SPLIT, '10': SPLIT, 'A': SPLIT},
    '7':  {'2': SPLIT, '3': SPLIT, '4': SPLIT, '5': SPLIT, '6': SPLIT, '7': SPLIT, '8': _NO_SPLIT, '9': _NO_SPLIT, '10': _NO_SPLIT, 'A': _NO_SPLIT},
    '6':  {'2': _COND_SPLIT, '3': SPLIT, '4': SPLIT, '5': SPLIT, '6': SPLIT, '7': _NO_SPLIT, '8': _NO_SPLIT, '9': _NO_SPLIT, '10': _NO_SPLIT, 'A': _NO_SPLIT},
    '5':  {'2': _NO_SPLIT, '3': _NO_SPLIT, '4': _NO_SPLIT, '5': _NO_SPLIT, '6': _NO_SPLIT, '7': _NO_SPLIT, '8': _NO_SPLIT, '9': _NO_SPLIT, '10': _NO_SPLIT, 'A': _NO_SPLIT},
    '4':  {'2': _NO_SPLIT, '3': _NO_SPLIT, '4': _NO_SPLIT, '5': _COND_SPLIT, '6': _COND_SPLIT, '7': _NO_SPLIT, '8': _NO_SPLIT, '9': _NO_SPLIT, '10': _NO_SPLIT, 'A': _NO_SPLIT},
    '3':  {'2': _COND_SPLIT, '3': _COND_SPLIT, '4': SPLIT, '5': SPLIT, '6': SPLIT, '7': SPLIT, '8': _NO_SPLIT, '9': _NO_SPLIT, '10': _NO_SPLIT, 'A': _NO_SPLIT},
    '2':  {'2': _COND_SPLIT, '3': _COND_SPLIT, '4': SPLIT, '5': SPLIT, '6': SPLIT, '7': SPLIT, '8': _NO_SPLIT, '9': _NO_SPLIT, '10': _NO_SPLIT, 'A': _NO_SPLIT},
}


def _downgrade(action: str, can_double: bool, can_split: bool) -> str:
    """
    Resolve a chart action/marker against RUNTIME hand-state legality.

    This is unrelated to `_resolve_das_pair_cell` — this function never
    looks at table rules, only at whether double/split is legal to perform
    on this specific hand right now (e.g. already hit once, already split).
    """
    if action == DOUBLE:
        return action if can_double else HIT
    if action == _DS:
        return DOUBLE if can_double else STAND
    if action == SPLIT:
        return action if can_split else HIT
    return action


def _hard_total_action(total: int, col: str, hard_table: dict) -> str:
    """Look up (or default-fallback) the hard-total chart action for a total/column."""
    if total in hard_table:
        return hard_table[total][col]
    if total <= 8:
        return HIT
    return STAND


def _pair_equivalent_hard_total(pair_rank: str) -> int:
    """The hard total a non-split pair plays as (e.g. 6,6 -> hard 12)."""
    return 2 * _rank_value(pair_rank)


def _resolve_das_pair_cell(pair_rank: str, col: str, double_after_split: bool, hard_table: dict) -> str:
    """
    Resolve a pairs-table cell using the table's ruleset (chart-lookup time).

    Y/N cells split only when double_after_split is True; otherwise — like
    plain N cells — the pair is never split and instead plays as its
    equivalent hard total (e.g. 4,4 = hard 8, always HIT).
    """
    cell = _PAIRS[pair_rank][col]
    if cell == SPLIT:
        return SPLIT
    if cell == _COND_SPLIT and double_after_split:
        return SPLIT
    return _hard_total_action(_pair_equivalent_hard_total(pair_rank), col, hard_table)


def correct_action(
    player_ranks: list[str],
    dealer_upcard_rank: str,
    dealer_hits_soft17: bool,
    double_after_split: bool,
    can_double: bool = True,
    can_split: bool = True,
) -> str:
    """
    Return the basic-strategy-correct action code (H/S/D/P) for a hand.

    Args:
        player_ranks:       list of the player's current card ranks (2+ cards)
        dealer_upcard_rank: the dealer's face-up card rank
        dealer_hits_soft17: True for H17 tables, False for S17 tables
        double_after_split: True if this table allows doubling after a split
                            (resolves 5 DAS-dependent pair cells)
        can_double:         whether doubling is a legal move right now
                            (typically only on the first two cards)
        can_split:          whether splitting is a legal move right now
                            (typically only on an initial pair)
    """
    if len(player_ranks) < 2:
        raise ValueError("correct_action requires at least 2 player cards")
    if dealer_upcard_rank not in RANKS_ORDER:
        raise ValueError(f"Unknown dealer upcard rank: {dealer_upcard_rank!r}")
    if not isinstance(dealer_hits_soft17, bool):
        raise ValueError(f"dealer_hits_soft17 must be a bool, got {dealer_hits_soft17!r}")
    if not isinstance(double_after_split, bool):
        raise ValueError(f"double_after_split must be a bool, got {double_after_split!r}")

    col = upcard_key(dealer_upcard_rank)
    hard_table = _HARD_TOTALS_H17 if dealer_hits_soft17 else _HARD_TOTALS_S17
    soft_table = _SOFT_TOTALS_H17 if dealer_hits_soft17 else _SOFT_TOTALS_S17

    if can_split and is_pair(player_ranks):
        pair_rank = '10' if player_ranks[0] in ('10', 'J', 'Q', 'K') else player_ranks[0]
        action = _resolve_das_pair_cell(pair_rank, col, double_after_split, hard_table)
        return _downgrade(action, can_double, can_split)

    total, soft = hand_total(player_ranks)

    if soft and total <= 20 and total in soft_table:
        action = soft_table[total][col]
        return _downgrade(action, can_double, can_split)

    action = _hard_total_action(total, col, hard_table)
    return _downgrade(action, can_double, can_split)
