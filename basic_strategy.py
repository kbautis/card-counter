"""
basic_strategy.py — Basic strategy chart lookup for the hand-play trainer.

Ruleset assumed (the most common multi-deck spread found at US casinos):
  - 4-8 decks
  - Dealer stands on soft 17 (S17)
  - Double after split allowed (DAS)
  - No surrender

All functions are pure and side-effect free. Preconditions fail fast.
"""

RANKS_ORDER = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

HIT, STAND, DOUBLE, SPLIT = 'H', 'S', 'D', 'P'

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


def _upcard_key(dealer_upcard_rank: str) -> str:
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
# Each table maps a row key -> dict of dealer-upcard-column -> action.
# Columns always present: 2,3,4,5,6,7,8,9,10,A

_HARD_TOTALS = {
    # totals 8 and below: always hit (not listed; default fallback)
    9:  {'2': HIT, '3': DOUBLE, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    10: {'2': DOUBLE, '3': DOUBLE, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': DOUBLE, '8': DOUBLE, '9': DOUBLE, '10': HIT, 'A': HIT},
    11: {'2': DOUBLE, '3': DOUBLE, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': DOUBLE, '8': DOUBLE, '9': DOUBLE, '10': DOUBLE, 'A': HIT},
    12: {'2': HIT, '3': HIT, '4': STAND, '5': STAND, '6': STAND, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    13: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': STAND, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    14: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': STAND, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    15: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': STAND, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    16: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': STAND, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    # 17+: always stand (not listed; default fallback)
}

_SOFT_TOTALS = {
    # soft 13 = A,2 ... soft 20 = A,9. Soft 21 (blackjack) is never a decision point.
    13: {'2': HIT, '3': HIT, '4': HIT, '5': DOUBLE, '6': DOUBLE, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    14: {'2': HIT, '3': HIT, '4': HIT, '5': DOUBLE, '6': DOUBLE, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    15: {'2': HIT, '3': HIT, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    16: {'2': HIT, '3': HIT, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    17: {'2': HIT, '3': DOUBLE, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    18: {'2': STAND, '3': DOUBLE, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': STAND, '8': STAND, '9': HIT, '10': HIT, 'A': HIT},
    19: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': DOUBLE, '7': STAND, '8': STAND, '9': STAND, '10': STAND, 'A': STAND},
    20: {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': STAND, '7': STAND, '8': STAND, '9': STAND, '10': STAND, 'A': STAND},
}

_PAIRS = {
    '2':  {'2': SPLIT, '3': SPLIT, '4': SPLIT, '5': SPLIT, '6': SPLIT, '7': SPLIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    '3':  {'2': SPLIT, '3': SPLIT, '4': SPLIT, '5': SPLIT, '6': SPLIT, '7': SPLIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    '4':  {'2': HIT, '3': HIT, '4': HIT, '5': SPLIT, '6': SPLIT, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    '5':  {'2': DOUBLE, '3': DOUBLE, '4': DOUBLE, '5': DOUBLE, '6': DOUBLE, '7': DOUBLE, '8': DOUBLE, '9': DOUBLE, '10': HIT, 'A': HIT},
    '6':  {'2': SPLIT, '3': SPLIT, '4': SPLIT, '5': SPLIT, '6': SPLIT, '7': HIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    '7':  {'2': SPLIT, '3': SPLIT, '4': SPLIT, '5': SPLIT, '6': SPLIT, '7': SPLIT, '8': HIT, '9': HIT, '10': HIT, 'A': HIT},
    '8':  {'2': SPLIT, '3': SPLIT, '4': SPLIT, '5': SPLIT, '6': SPLIT, '7': SPLIT, '8': SPLIT, '9': SPLIT, '10': SPLIT, 'A': SPLIT},
    '9':  {'2': SPLIT, '3': SPLIT, '4': SPLIT, '5': SPLIT, '6': SPLIT, '7': STAND, '8': SPLIT, '9': SPLIT, '10': STAND, 'A': STAND},
    '10': {'2': STAND, '3': STAND, '4': STAND, '5': STAND, '6': STAND, '7': STAND, '8': STAND, '9': STAND, '10': STAND, 'A': STAND},
    'A':  {'2': SPLIT, '3': SPLIT, '4': SPLIT, '5': SPLIT, '6': SPLIT, '7': SPLIT, '8': SPLIT, '9': SPLIT, '10': SPLIT, 'A': SPLIT},
}


def _downgrade(action: str, can_double: bool, can_split: bool) -> str:
    """If the chart says Double/Split but that move isn't legal, fall back."""
    if action == DOUBLE and not can_double:
        return HIT
    if action == SPLIT and not can_split:
        return HIT
    return action


def correct_action(
    player_ranks: list[str],
    dealer_upcard_rank: str,
    can_double: bool = True,
    can_split: bool = True,
) -> str:
    """
    Return the basic-strategy-correct action code (H/S/D/P) for a hand.

    Args:
        player_ranks:       list of the player's current card ranks (2+ cards)
        dealer_upcard_rank: the dealer's face-up card rank
        can_double:         whether doubling is a legal move right now
                            (typically only on the first two cards)
        can_split:          whether splitting is a legal move right now
                            (typically only on an initial pair)
    """
    if len(player_ranks) < 2:
        raise ValueError("correct_action requires at least 2 player cards")
    if dealer_upcard_rank not in RANKS_ORDER:
        raise ValueError(f"Unknown dealer upcard rank: {dealer_upcard_rank!r}")

    col = _upcard_key(dealer_upcard_rank)

    # Pair logic only applies on the initial two cards.
    if can_split and is_pair(player_ranks):
        pair_rank = '10' if player_ranks[0] in ('10', 'J', 'Q', 'K') else player_ranks[0]
        action = _PAIRS[pair_rank][col]
        return _downgrade(action, can_double, can_split)

    total, soft = hand_total(player_ranks)

    if soft and total <= 20 and total in _SOFT_TOTALS:
        action = _SOFT_TOTALS[total][col]
        return _downgrade(action, can_double, can_split)

    if total >= 17:
        return STAND
    if total <= 8:
        return HIT
    action = _HARD_TOTALS[total][col]
    return _downgrade(action, can_double, can_split)
