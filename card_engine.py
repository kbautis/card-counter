"""
card_engine.py — Core logic for the card counting trainer.

Responsibilities:
- Deck/shoe generation and shuffling
- Hi-Lo card value lookup
- Running count and true count calculation
- Session creation and answer verification

Each function has a single responsibility. All preconditions fail fast.
"""
import random

RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
SUITS = ['hearts', 'diamonds', 'clubs', 'spades']
MAX_DECKS = 8
MIN_CARDS  = 5   # minimum cards that can be dealt in a session

HI_LO_VALUES = {
    '2': +1, '3': +1, '4': +1, '5': +1, '6': +1,
    '7':  0, '8':  0, '9':  0,
    '10': -1, 'J': -1, 'Q': -1, 'K': -1, 'A': -1,
}


def generate_shoe(num_decks: int) -> list[dict]:
    """Return a shuffled shoe of `num_decks` standard 52-card decks."""
    if not isinstance(num_decks, int) or num_decks < 1 or num_decks > MAX_DECKS:
        raise ValueError(
            f"num_decks must be an integer between 1 and {MAX_DECKS}, got {num_decks!r}"
        )

    shoe = [
        {'rank': rank, 'suit': suit}
        for _ in range(num_decks)
        for rank in RANKS
        for suit in SUITS
    ]
    random.shuffle(shoe)
    return shoe


def hi_lo_value(card: dict) -> int:
    """Return the Hi-Lo count value (+1, 0, -1) for a single card."""
    if 'rank' not in card:
        raise ValueError(f"Card is missing 'rank' key: {card!r}")
    rank = card['rank']
    if rank not in HI_LO_VALUES:
        raise ValueError(f"Unknown card rank: {rank!r}")
    return HI_LO_VALUES[rank]


def calculate_count(cards: list[dict]) -> int:
    """Return the running Hi-Lo count for a list of cards."""
    return sum(hi_lo_value(card) for card in cards)


def calculate_true_count(
    running_count: int,
    total_shoe_cards: int,
    cards_dealt: int,
) -> float | None:
    """
    Return the true count (running count ÷ decks remaining).

    The true count normalises the running count to a per-deck basis,
    which is what players actually act on in multi-deck games.

    Returns None when the full shoe has been dealt (no decks remain).
    """
    cards_remaining = total_shoe_cards - cards_dealt
    if cards_remaining <= 0:
        return None
    decks_remaining = cards_remaining / 52
    return running_count / decks_remaining


def create_session(
    num_decks: int,
    interval_ms: int,
    num_cards: int | None = None,
) -> dict:
    """
    Create a new game session.

    Args:
        num_decks:   Number of decks in the shoe (1–8).
        interval_ms: Card-flip interval in milliseconds (> 0).
        num_cards:   Cards to actually deal. Defaults to full shoe.
                     Must be between MIN_CARDS and the full shoe size.

    Returns a dict containing:
      - cards:           the dealt cards (full shoe or sliced to num_cards)
      - hi_lo_values:    list of Hi-Lo values for each dealt card
      - correct_count:   running Hi-Lo count for the dealt cards
      - num_decks:       number of decks in the shoe
      - interval_ms:     card-flip interval in milliseconds
      - total_shoe_size: total cards in the full uncut shoe
      - cards_dealt:     number of cards actually dealt (= len(cards))
    """
    if not isinstance(interval_ms, int) or interval_ms <= 0:
        raise ValueError(f"interval_ms must be a positive integer, got {interval_ms!r}")

    shoe = generate_shoe(num_decks)  # num_decks validated inside generate_shoe
    total_shoe_size = len(shoe)

    if num_cards is not None:
        if not isinstance(num_cards, int) or not (MIN_CARDS <= num_cards <= total_shoe_size):
            raise ValueError(
                f"num_cards must be an integer between {MIN_CARDS} and "
                f"{total_shoe_size}, got {num_cards!r}"
            )
        shoe = shoe[:num_cards]

    dealt = shoe
    return {
        'cards':           dealt,
        'hi_lo_values':    [hi_lo_value(c) for c in dealt],
        'correct_count':   calculate_count(dealt),
        'num_decks':       num_decks,
        'interval_ms':     interval_ms,
        'total_shoe_size': total_shoe_size,
        'cards_dealt':     len(dealt),
    }


def verify_answer(correct_count: int, user_count: int) -> dict:
    """
    Compare the user's submitted count against the correct count.

    Returns a result dict with:
      - correct:       bool
      - correct_count: int
      - user_count:    int
      - delta:         absolute difference
    """
    return {
        'correct':       user_count == correct_count,
        'correct_count': correct_count,
        'user_count':    user_count,
        'delta':         abs(correct_count - user_count),
    }
