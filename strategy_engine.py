"""
strategy_engine.py — Hand-play session engine for the Basic Strategy trainer.

Responsibilities:
- Deal shoes with penetration-based reshuffling
- Run a player through num_hands of hit/stand/double/split decisions
- Score each decision against basic_strategy.correct_action
- Play the dealer out (stands on soft 17) and resolve win/loss/push

Splits are scored for strategy correctness but not played out into two
sub-hands — a common, deliberate simplification in count/strategy trainers
that keeps the state machine linear while still covering the ~92% of hands
that aren't pairs end-to-end (deal → decisions → dealer resolution).

Each function has a single responsibility. All preconditions fail fast.
"""
from card_engine import generate_shoe
from basic_strategy import correct_action, hand_total, is_pair, HIT, STAND, DOUBLE, SPLIT

MIN_HANDS = 1
MAX_HANDS = 100
DEFAULT_PENETRATION = 0.75
MIN_RESHUFFLE_CUSHION = 15  # never deal a new hand with fewer cards left than this


def _validate_new_session_args(num_decks: int, num_hands: int, penetration: float) -> None:
    if not isinstance(num_decks, int) or not (1 <= num_decks <= 8):
        raise ValueError(f"num_decks must be an integer between 1 and 8, got {num_decks!r}")
    if not isinstance(num_hands, int) or not (MIN_HANDS <= num_hands <= MAX_HANDS):
        raise ValueError(
            f"num_hands must be an integer between {MIN_HANDS} and {MAX_HANDS}, got {num_hands!r}"
        )
    if not isinstance(penetration, (int, float)) or not (0 < penetration <= 1):
        raise ValueError(f"penetration must be a number in (0, 1], got {penetration!r}")


def _draw_card(state: dict) -> dict:
    """Pop a card from the shoe, reshuffling a fresh shoe if it runs dry mid-hand."""
    if not state['shoe']:
        state['shoe'] = generate_shoe(state['num_decks'])
        state['mid_hand_reshuffles'] += 1
    return state['shoe'].pop()


def _deal_new_hand(state: dict) -> None:
    """Reshuffle if past the penetration cutoff, then deal a fresh player/dealer hand."""
    if len(state['shoe']) < state['cutoff']:
        state['shoe'] = generate_shoe(state['num_decks'])
        state['shuffles'] += 1

    player_cards = [_draw_card(state), _draw_card(state)]
    dealer_cards = [_draw_card(state), _draw_card(state)]

    state['current_hand'] = {
        'player_cards':       player_cards,
        'dealer_cards':       dealer_cards,
        'dealer_hole_hidden': True,
        'stage':              'player_turn',
        'can_double':         True,
        'can_split':          is_pair([c['rank'] for c in player_cards]),
    }


def create_session(
    num_decks: int,
    num_hands: int,
    penetration: float = DEFAULT_PENETRATION,
) -> dict:
    """
    Create a new basic-strategy session and deal the first hand.

    Returns the full internal state dict (callers persist this server-side;
    use public_session_view() to build the client-facing JSON payload).
    """
    _validate_new_session_args(num_decks, num_hands, penetration)

    shoe = generate_shoe(num_decks)
    shoe_size = len(shoe)
    cutoff = max(MIN_RESHUFFLE_CUSHION, int(round(shoe_size * (1 - penetration))))

    state = {
        'num_decks':          num_decks,
        'num_hands':          num_hands,
        'penetration':        penetration,
        'shoe':               shoe,
        'shoe_size':          shoe_size,
        'cutoff':             cutoff,
        'shuffles':           0,
        'mid_hand_reshuffles': 0,
        'hands_played':       0,
        'correct_decisions':  0,
        'total_decisions':    0,
        'wins':               0,
        'losses':             0,
        'pushes':             0,
        'current_hand':       None,
        'done':               False,
    }
    _deal_new_hand(state)
    return state


def _resolve_vs_dealer(state: dict, hand: dict, result: dict, dealer_plays: bool) -> None:
    """Reveal the dealer's hole card, optionally play the dealer out, and score the hand."""
    hand['dealer_hole_hidden'] = False
    player_total, _ = hand_total([c['rank'] for c in hand['player_cards']])

    if not dealer_plays:
        # Player already busted — no need to draw further, just report the hand.
        dealer_total, _ = hand_total([c['rank'] for c in hand['dealer_cards']])
        result['dealer_total']  = dealer_total
        result['player_total']  = player_total
        result['dealer_cards']  = hand['dealer_cards']
        result['player_cards']  = hand['player_cards']
        return

    dealer_ranks = [c['rank'] for c in hand['dealer_cards']]
    while True:
        total, soft = hand_total(dealer_ranks)
        if total >= 17:  # dealer stands on soft 17 (S17)
            break
        card = _draw_card(state)
        hand['dealer_cards'].append(card)
        dealer_ranks.append(card['rank'])

    dealer_total, _ = hand_total(dealer_ranks)

    if dealer_total > 21 or dealer_total < player_total:
        outcome = 'win'
        state['wins'] += 1
    elif dealer_total > player_total:
        outcome = 'loss'
        state['losses'] += 1
    else:
        outcome = 'push'
        state['pushes'] += 1

    result['outcome']      = outcome
    result['dealer_total'] = dealer_total
    result['player_total'] = player_total
    result['dealer_cards'] = hand['dealer_cards']
    result['player_cards'] = hand['player_cards']


def _finish_hand(state: dict, result: dict) -> None:
    state['current_hand']['stage'] = 'done'
    state['hands_played'] += 1
    result['hand_finished'] = True

    if state['hands_played'] >= state['num_hands']:
        state['done'] = True
        state['current_hand'] = None
    else:
        _deal_new_hand(state)


def apply_action(state: dict, action_code: str) -> dict:
    """
    Apply a player decision (H/S/D/P) to the in-progress hand.

    Scores the decision against basic strategy, mutates state (drawing
    cards, resolving the hand, dealing the next one when applicable), and
    returns a result dict describing what happened.
    """
    if action_code not in (HIT, STAND, DOUBLE, SPLIT):
        raise ValueError(f"Unknown action code: {action_code!r}")

    hand = state['current_hand']
    if hand is None or hand['stage'] != 'player_turn':
        raise ValueError("No hand is awaiting a decision")

    player_ranks    = [c['rank'] for c in hand['player_cards']]
    dealer_up_rank  = hand['dealer_cards'][0]['rank']
    ideal           = correct_action(
        player_ranks, dealer_up_rank,
        can_double=hand['can_double'], can_split=hand['can_split'],
    )
    was_correct = action_code == ideal

    state['total_decisions'] += 1
    if was_correct:
        state['correct_decisions'] += 1

    result = {
        'action_taken':   action_code,
        'correct_action': ideal,
        'was_correct':    was_correct,
        'hand_finished':  False,
        'outcome':        None,
        'drawn_card':     None,
    }

    if action_code == SPLIT:
        if not hand['can_split']:
            raise ValueError("Split is not a legal move right now")
        result['outcome'] = 'split'  # scored only — see module docstring
        result['player_cards'] = hand['player_cards']
        # Dealer's hole card is never revealed for a scored-only split — the
        # hand was never actually played out against the dealer.
        result['dealer_cards'] = [hand['dealer_cards'][0]]
        _finish_hand(state, result)

    elif action_code == DOUBLE:
        if not hand['can_double']:
            raise ValueError("Double is not a legal move right now")
        card = _draw_card(state)
        hand['player_cards'].append(card)
        result['drawn_card'] = card
        total, _ = hand_total([c['rank'] for c in hand['player_cards']])
        if total > 21:
            result['outcome'] = 'loss'
            state['losses'] += 1
            _resolve_vs_dealer(state, hand, result, dealer_plays=False)
        else:
            _resolve_vs_dealer(state, hand, result, dealer_plays=True)
        _finish_hand(state, result)

    elif action_code == HIT:
        card = _draw_card(state)
        hand['player_cards'].append(card)
        hand['can_double'] = False
        hand['can_split']  = False
        result['drawn_card'] = card
        total, _ = hand_total([c['rank'] for c in hand['player_cards']])
        if total > 21:
            result['outcome'] = 'loss'
            state['losses'] += 1
            _resolve_vs_dealer(state, hand, result, dealer_plays=False)
            _finish_hand(state, result)
        # else: hand stays open, player_turn continues

    elif action_code == STAND:
        _resolve_vs_dealer(state, hand, result, dealer_plays=True)
        _finish_hand(state, result)

    return result


def public_hand_view(hand: dict | None) -> dict | None:
    """Client-facing view of a hand — hides the dealer's hole card while hidden."""
    if hand is None:
        return None
    player_total, player_soft = hand_total([c['rank'] for c in hand['player_cards']])
    view = {
        'player_cards':  hand['player_cards'],
        'player_total':  player_total,
        'player_soft':   player_soft,
        'dealer_upcard': hand['dealer_cards'][0],
        'can_double':    hand['can_double'],
        'can_split':     hand['can_split'],
        'stage':         hand['stage'],
    }
    if hand['dealer_hole_hidden']:
        view['dealer_cards'] = [hand['dealer_cards'][0]]
    else:
        dealer_total, _ = hand_total([c['rank'] for c in hand['dealer_cards']])
        view['dealer_cards'] = hand['dealer_cards']
        view['dealer_total'] = dealer_total
    return view


def public_session_view(state: dict) -> dict:
    """Client-facing summary of session progress (no shoe contents exposed)."""
    return {
        'num_decks':         state['num_decks'],
        'num_hands':         state['num_hands'],
        'hands_played':      state['hands_played'],
        'correct_decisions': state['correct_decisions'],
        'total_decisions':   state['total_decisions'],
        'wins':              state['wins'],
        'losses':            state['losses'],
        'pushes':            state['pushes'],
        'done':              state['done'],
        'hand':              public_hand_view(state['current_hand']),
    }
