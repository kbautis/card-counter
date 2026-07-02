"""
strategy_engine.py — Multi-spot, live-table session engine for the Basic
Strategy trainer.

Architecture note (system-architect, Tasks 2-7):
  - A session now plays open-ended ROUNDS (not a fixed hand count). Each
    round deals `num_hands` independent SPOTS plus one dealer hand. A spot
    starts as one HAND, and becomes two independently playable hands if the
    player splits (Task 4) — no re-splitting, a deliberate simplification.
  - Turn order is a single "cursor": `current_round['active_spot_index'] /
    active_hand_index` always points at the one hand currently awaiting a
    decision, advancing spot-by-spot, hand-by-hand within a split spot, then
    to a single once-per-round dealer play that resolves every hand still
    live (`_run_dealer_turn`). This keeps the state machine linear even
    though multiple hands are in flight.
  - Dealer peek + player naturals happen once per round in `_deal_new_round`,
    strictly in that order (peek/dealer-blackjack first, since it can end
    the round with zero decisions offered; naturals second, since they only
    matter once we know the dealer doesn't already have blackjack).
  - Hi-Lo running count is accumulated here (Task 6) by reusing
    card_engine.hi_lo_value/calculate_true_count — never reimplemented. The
    dealer's hole card is drawn but NOT counted until it's actually revealed
    (`_reveal_dealer_hole`), matching real-table counting practice.
  - Deviation scoring (Task 6) is tracked in separate counters
    (`deviation_correct`/`deviation_total`) from base strategy accuracy
    (`correct_decisions`/`total_decisions`) — a live-mode decision is two
    independent judgments ("basic-strategy-correct?" and, only if an
    Illustrious 18 entry applies here, "count-correct?"), not one blended
    score.

Each function has a single responsibility. All preconditions fail fast.
"""
from card_engine import generate_shoe, hi_lo_value, calculate_true_count
from basic_strategy import correct_action, hand_total, is_pair, upcard_key, HIT, STAND, DOUBLE, SPLIT
from deviations import hand_description, deviation_lookup, deviation_triggered

MIN_HANDS = 1
MAX_HANDS = 6  # simultaneous spots per round — realistic cap for a full live table
DEFAULT_PENETRATION = 0.75
MIN_RESHUFFLE_CUSHION = 15  # never deal a new round with fewer cards left than this
MAX_ROUNDS = 500  # generous safety cap so an unattended/forgotten session can't grow forever


def _validate_new_session_args(
    num_decks: int, num_hands: int, penetration: float,
    dealer_hits_soft17: bool, double_after_split: bool, live_mode: bool,
) -> None:
    if not isinstance(num_decks, int) or not (1 <= num_decks <= 8):
        raise ValueError(f"num_decks must be an integer between 1 and 8, got {num_decks!r}")
    if not isinstance(num_hands, int) or not (MIN_HANDS <= num_hands <= MAX_HANDS):
        raise ValueError(
            f"num_hands must be an integer between {MIN_HANDS} and {MAX_HANDS}, got {num_hands!r}"
        )
    if not isinstance(penetration, (int, float)) or not (0 < penetration <= 1):
        raise ValueError(f"penetration must be a number in (0, 1], got {penetration!r}")
    if not isinstance(dealer_hits_soft17, bool):
        raise ValueError(f"dealer_hits_soft17 must be a bool, got {dealer_hits_soft17!r}")
    if not isinstance(double_after_split, bool):
        raise ValueError(f"double_after_split must be a bool, got {double_after_split!r}")
    if not isinstance(live_mode, bool):
        raise ValueError(f"live_mode must be a bool, got {live_mode!r}")


def _draw_card(state: dict) -> dict:
    """Pop a card from the shoe, reshuffling a fresh shoe if it runs dry mid-round."""
    if not state['shoe']:
        state['shoe'] = generate_shoe(state['num_decks'])
        state['shoe_size'] = len(state['shoe'])
        state['mid_hand_reshuffles'] += 1
    return state['shoe'].pop()


def _count_card(state: dict, card: dict) -> None:
    """Fold a just-revealed card into the running count, if Live mode is on."""
    if state['live_mode']:
        state['running_count'] += hi_lo_value(card)


def _draw_and_count(state: dict) -> dict:
    card = _draw_card(state)
    _count_card(state, card)
    return card


def _new_hand(player_cards: list[dict], can_double: bool, can_split: bool, is_split_hand: bool) -> dict:
    return {
        'player_cards':  player_cards,
        'stage':         'player_turn',
        'can_double':    can_double,
        'can_split':     can_split,
        'is_split_hand': is_split_hand,
        'hint_used':     False,
        'outcome':       None,
    }


def _reveal_dealer_hole(state: dict, round_: dict) -> None:
    if round_['dealer_hole_hidden']:
        round_['dealer_hole_hidden'] = False
        _count_card(state, round_['dealer_cards'][1])


def _run_dealer_turn(state: dict, round_: dict) -> None:
    """Play the dealer's single hand once, then resolve every hand still awaiting it."""
    _reveal_dealer_hole(state, round_)

    live_hands = [h for spot in round_['spots'] for h in spot['hands'] if h['stage'] == 'awaiting_dealer']
    if live_hands:
        dealer_ranks = [c['rank'] for c in round_['dealer_cards']]
        while True:
            total, soft = hand_total(dealer_ranks)
            must_hit = total < 17 or (total == 17 and soft and state['dealer_hits_soft17'])
            if not must_hit:
                break
            card = _draw_and_count(state)
            round_['dealer_cards'].append(card)
            dealer_ranks.append(card['rank'])
        dealer_total, _ = hand_total(dealer_ranks)

        for hand in live_hands:
            player_total, _ = hand_total([c['rank'] for c in hand['player_cards']])
            if dealer_total > 21 or player_total > dealer_total:
                hand['outcome'] = 'win'
                state['wins'] += 1
            elif player_total < dealer_total:
                hand['outcome'] = 'loss'
                state['losses'] += 1
            else:
                hand['outcome'] = 'push'
                state['pushes'] += 1
            hand['stage'] = 'done'
            state['hands_played'] += 1

    for spot in round_['spots']:
        spot['resolved'] = all(h['stage'] == 'done' for h in spot['hands'])

    round_['stage'] = 'done'


def _advance_active_hand(state: dict, round_: dict) -> None:
    """Point the cursor at the next hand awaiting a decision, or run the dealer's turn."""
    for spot_index, spot in enumerate(round_['spots']):
        for hand_index, hand in enumerate(spot['hands']):
            if hand['stage'] == 'player_turn':
                round_['active_spot_index'] = spot_index
                round_['active_hand_index'] = hand_index
                return
    round_['active_spot_index'] = None
    round_['active_hand_index'] = None
    _run_dealer_turn(state, round_)


def _deal_new_round(state: dict) -> None:
    """Reshuffle if past the penetration cutoff, then deal a fresh round to every spot."""
    if len(state['shoe']) < state['cutoff']:
        state['shoe'] = generate_shoe(state['num_decks'])
        state['shoe_size'] = len(state['shoe'])
        state['shuffles'] += 1

    num_spots = state['num_hands']
    spot_cards = [[] for _ in range(num_spots)]
    dealer_cards = []

    # Deal like a live table: one card to each spot then the dealer, twice.
    for round_of_two in range(2):
        for cards in spot_cards:
            cards.append(_draw_and_count(state))
        card = _draw_card(state)
        if round_of_two == 0:
            _count_card(state, card)  # up-card counts immediately
        # else: hole card — deliberately NOT counted until revealed
        dealer_cards.append(card)

    spots = [
        {
            'hands': [_new_hand(cards, can_double=True, can_split=is_pair([c['rank'] for c in cards]),
                                 is_split_hand=False)],
            'natural': False,
            'resolved': False,
        }
        for cards in spot_cards
    ]

    dealer_upcard_rank = dealer_cards[0]['rank']
    should_peek = upcard_key(dealer_upcard_rank) in ('10', 'A')
    dealer_total, _ = hand_total([c['rank'] for c in dealer_cards])
    dealer_blackjack = should_peek and dealer_total == 21

    round_ = {
        'spots':              spots,
        'dealer_cards':       dealer_cards,
        'dealer_hole_hidden': True,
        'dealer_blackjack':   dealer_blackjack if should_peek else None,
        'stage':              'player_decisions',
        'active_spot_index':  None,
        'active_hand_index':  None,
    }
    state['current_round'] = round_

    if dealer_blackjack:
        _reveal_dealer_hole(state, round_)
        for spot in spots:
            hand = spot['hands'][0]
            player_total, _ = hand_total([c['rank'] for c in hand['player_cards']])
            hand['outcome'] = 'push' if player_total == 21 else 'loss'
            if hand['outcome'] == 'push':
                state['pushes'] += 1
            else:
                state['losses'] += 1
            hand['stage'] = 'done'
            state['hands_played'] += 1
            spot['resolved'] = True
        round_['stage'] = 'done'
        _finish_round(state)
        return

    for spot in spots:
        hand = spot['hands'][0]
        total, _ = hand_total([c['rank'] for c in hand['player_cards']])
        if total == 21:
            spot['natural'] = True
            hand['outcome'] = 'win'
            state['wins'] += 1
            hand['stage'] = 'done'
            state['hands_played'] += 1
            spot['resolved'] = True

    _advance_active_hand(state, round_)
    if round_['stage'] == 'done':
        _finish_round(state)


def _finish_round(state: dict) -> None:
    state['rounds_played'] += 1
    if state['rounds_played'] >= MAX_ROUNDS:
        state['done'] = True
        state['current_round'] = None
    else:
        _deal_new_round(state)


def create_session(
    num_decks: int,
    num_hands: int,
    penetration: float = DEFAULT_PENETRATION,
    dealer_hits_soft17: bool = False,
    double_after_split: bool = True,
    live_mode: bool = False,
) -> dict:
    """
    Create a new basic-strategy session and deal the first round.

    Returns the full internal state dict (callers persist this server-side;
    use public_session_view() to build the client-facing JSON payload).
    """
    _validate_new_session_args(
        num_decks, num_hands, penetration, dealer_hits_soft17, double_after_split, live_mode,
    )

    shoe = generate_shoe(num_decks)
    shoe_size = len(shoe)
    cutoff = max(MIN_RESHUFFLE_CUSHION, int(round(shoe_size * (1 - penetration))))

    state = {
        'num_decks':           num_decks,
        'num_hands':            num_hands,
        'penetration':          penetration,
        'dealer_hits_soft17':   dealer_hits_soft17,
        'double_after_split':   double_after_split,
        'live_mode':            live_mode,
        'shoe':                 shoe,
        'shoe_size':            shoe_size,
        'cutoff':               cutoff,
        'shuffles':             0,
        'mid_hand_reshuffles':  0,
        'rounds_played':        0,
        'hands_played':         0,
        'correct_decisions':    0,
        'total_decisions':      0,
        'wins':                 0,
        'losses':               0,
        'pushes':               0,
        'hint_used_count':      0,
        'deviation_correct':    0,
        'deviation_total':      0,
        'running_count':        0 if live_mode else None,
        'current_round':        None,
        'done':                 False,
    }
    _deal_new_round(state)
    return state


def _active_hand(state: dict) -> tuple[dict, dict] | tuple[None, None]:
    round_ = state['current_round']
    if round_ is None or round_['active_spot_index'] is None:
        return None, None
    spot = round_['spots'][round_['active_spot_index']]
    hand = spot['hands'][round_['active_hand_index']]
    return spot, hand


def request_hint(state: dict) -> dict:
    """
    Return the correct action for the active hand WITHOUT mutating game
    state, and flag that hand as hint-used (Task 5). Flagging is idempotent
    — asking twice for the same hand only counts once in hint_used_count.
    """
    spot, hand = _active_hand(state)
    if hand is None:
        raise ValueError("No hand is awaiting a decision")

    round_ = state['current_round']
    dealer_up_rank = round_['dealer_cards'][0]['rank']
    player_ranks = [c['rank'] for c in hand['player_cards']]
    ideal = correct_action(
        player_ranks, dealer_up_rank, state['dealer_hits_soft17'], state['double_after_split'],
        can_double=hand['can_double'], can_split=hand['can_split'],
    )
    if not hand['hint_used']:
        hand['hint_used'] = True
        state['hint_used_count'] += 1
    return {'action': ideal, 'hint_used': True}


def check_count(state: dict) -> dict:
    """On-demand running/true count reveal (Task 6) — never pushed automatically."""
    if not state['live_mode']:
        raise ValueError("Live mode is not enabled for this session")
    cards_dealt = state['shoe_size'] - len(state['shoe'])
    true_count = calculate_true_count(state['running_count'], state['shoe_size'], cards_dealt)
    return {
        'running_count': state['running_count'],
        'true_count':    round(true_count, 2) if true_count is not None else None,
    }


def _score_deviation(state: dict, hand: dict, dealer_up_rank: str, action_code: str, base_ideal: str) -> dict:
    """
    If an Illustrious 18 entry applies to this exact decision (and the
    deviate-to move is currently legal), score it — separately from base
    strategy accuracy (see module docstring).
    """
    description = hand_description([c['rank'] for c in hand['player_cards']], hand['can_split'])
    entry = deviation_lookup(description, upcard_key(dealer_up_rank))
    if entry is None:
        return {'deviation_applicable': False}

    deviate_to = entry['deviate_to']
    legal = (deviate_to != DOUBLE or hand['can_double']) and (deviate_to != SPLIT or hand['can_split'])
    if not legal:
        return {'deviation_applicable': False}

    cards_dealt = state['shoe_size'] - len(state['shoe'])
    true_count = calculate_true_count(state['running_count'], state['shoe_size'], cards_dealt)
    true_count = true_count if true_count is not None else 0.0

    deviation_correct_play = deviate_to if deviation_triggered(entry, true_count) else base_ideal
    deviation_was_correct = action_code == deviation_correct_play

    state['deviation_total'] += 1
    if deviation_was_correct:
        state['deviation_correct'] += 1

    return {
        'deviation_applicable':    True,
        'deviation_correct_action': deviation_correct_play,
        'deviation_was_correct':   deviation_was_correct,
        'true_count_at_decision':  round(true_count, 2),
    }


def apply_action(state: dict, action_code: str) -> dict:
    """
    Apply a player decision (H/S/D/P) to the hand currently awaiting one.

    Scores the decision against basic strategy (and, in Live mode, against
    the Illustrious 18 deviation table), mutates state (drawing cards,
    resolving hands, playing the dealer once all spots are settled, dealing
    the next round when applicable), and returns a result dict describing
    what happened.
    """
    if action_code not in (HIT, STAND, DOUBLE, SPLIT):
        raise ValueError(f"Unknown action code: {action_code!r}")

    spot, hand = _active_hand(state)
    if hand is None or hand['stage'] != 'player_turn':
        raise ValueError("No hand is awaiting a decision")

    round_ = state['current_round']
    dealer_up_rank = round_['dealer_cards'][0]['rank']
    player_ranks = [c['rank'] for c in hand['player_cards']]
    ideal = correct_action(
        player_ranks, dealer_up_rank, state['dealer_hits_soft17'], state['double_after_split'],
        can_double=hand['can_double'], can_split=hand['can_split'],
    )
    was_correct = action_code == ideal

    state['total_decisions'] += 1
    if was_correct:
        state['correct_decisions'] += 1

    result = {
        'action_taken':     action_code,
        'correct_action':   ideal,
        'was_correct':      was_correct,
        'hint_used':        hand['hint_used'],
        'spot_index':       state['current_round']['active_spot_index'],
        'hand_index':       state['current_round']['active_hand_index'],
        'hand_finished':    False,
        'outcome':          None,
        'drawn_card':       None,
    }
    if state['live_mode']:
        result.update(_score_deviation(state, hand, dealer_up_rank, action_code, ideal))

    if action_code == SPLIT:
        if not hand['can_split']:
            raise ValueError("Split is not a legal move right now")
        card_a, card_b = hand['player_cards']
        new_card_1 = _draw_and_count(state)
        new_card_2 = _draw_and_count(state)
        hand_1 = _new_hand([card_a, new_card_1], can_double=state['double_after_split'],
                            can_split=False, is_split_hand=True)
        hand_2 = _new_hand([card_b, new_card_2], can_double=state['double_after_split'],
                            can_split=False, is_split_hand=True)
        spot['hands'] = [hand_1, hand_2]
        round_['active_hand_index'] = 0
        result['outcome'] = 'split'
        result['new_hands'] = [hand_1['player_cards'], hand_2['player_cards']]

    elif action_code == DOUBLE:
        if not hand['can_double']:
            raise ValueError("Double is not a legal move right now")
        card = _draw_and_count(state)
        hand['player_cards'].append(card)
        result['drawn_card'] = card
        total, _ = hand_total([c['rank'] for c in hand['player_cards']])
        if total > 21:
            hand['outcome'] = 'loss'
            state['losses'] += 1
            hand['stage'] = 'done'
            state['hands_played'] += 1
        else:
            hand['stage'] = 'awaiting_dealer'
        result['hand_finished'] = True
        _advance_active_hand(state, round_)
        result['outcome'] = hand['outcome']
        result['player_cards'] = hand['player_cards']

    elif action_code == HIT:
        card = _draw_and_count(state)
        hand['player_cards'].append(card)
        hand['can_double'] = False
        hand['can_split'] = False
        result['drawn_card'] = card
        total, _ = hand_total([c['rank'] for c in hand['player_cards']])
        if total > 21:
            hand['outcome'] = 'loss'
            state['losses'] += 1
            hand['stage'] = 'done'
            state['hands_played'] += 1
            result['hand_finished'] = True
            _advance_active_hand(state, round_)
            result['outcome'] = hand['outcome']
            result['player_cards'] = hand['player_cards']
        # else: hand stays open, player_turn continues

    elif action_code == STAND:
        hand['stage'] = 'awaiting_dealer'
        result['hand_finished'] = True
        _advance_active_hand(state, round_)
        result['outcome'] = hand['outcome']
        result['player_cards'] = hand['player_cards']

    if not round_['dealer_hole_hidden']:
        dealer_total, _ = hand_total([c['rank'] for c in round_['dealer_cards']])
        result['dealer_cards'] = round_['dealer_cards']
        result['dealer_total'] = dealer_total

    if round_['stage'] == 'done':
        result['round_finished'] = True
        _finish_round(state)
    else:
        result['round_finished'] = False

    return result


def build_summary(state: dict) -> dict:
    """The Task 7 summary payload shape — shared by stop_session() and a natural session end."""
    total = state['total_decisions']
    summary = {
        'rounds_played':      state['rounds_played'],
        'hands_played':       state['hands_played'],
        'wins':                state['wins'],
        'losses':              state['losses'],
        'pushes':              state['pushes'],
        'correct_decisions':   state['correct_decisions'],
        'total_decisions':     total,
        'accuracy':            round(state['correct_decisions'] / total * 100, 1) if total else 0.0,
        'hint_used_count':     state['hint_used_count'],
    }
    if state['live_mode']:
        dtotal = state['deviation_total']
        summary['deviation_correct'] = state['deviation_correct']
        summary['deviation_total']   = dtotal
        summary['deviation_accuracy'] = round(state['deviation_correct'] / dtotal * 100, 1) if dtotal else 0.0
    return summary


def stop_session(state: dict) -> dict:
    """End the session immediately (mid-round is fine) and return the summary payload."""
    summary = build_summary(state)
    state['done'] = True
    state['current_round'] = None
    return summary


def public_hand_view(hand: dict | None) -> dict | None:
    if hand is None:
        return None
    total, soft = hand_total([c['rank'] for c in hand['player_cards']])
    return {
        'player_cards':  hand['player_cards'],
        'player_total':  total,
        'player_soft':   soft,
        'stage':         hand['stage'],
        'can_double':    hand['can_double'],
        'can_split':     hand['can_split'],
        'is_split_hand': hand['is_split_hand'],
        'hint_used':     hand['hint_used'],
        'outcome':       hand['outcome'],
    }


def public_spot_view(spot: dict) -> dict:
    return {
        'hands':   [public_hand_view(h) for h in spot['hands']],
        'natural': spot['natural'],
    }


def public_round_view(round_: dict | None) -> dict | None:
    """Client-facing view of the round — hides the dealer's hole card while hidden."""
    if round_ is None:
        return None
    view = {
        'spots':              [public_spot_view(s) for s in round_['spots']],
        'stage':               round_['stage'],
        'active_spot_index':   round_['active_spot_index'],
        'active_hand_index':   round_['active_hand_index'],
    }
    if round_['dealer_hole_hidden']:
        view['dealer_cards'] = [round_['dealer_cards'][0]]
    else:
        dealer_total, _ = hand_total([c['rank'] for c in round_['dealer_cards']])
        view['dealer_cards'] = round_['dealer_cards']
        view['dealer_total'] = dealer_total
    return view


def public_session_view(state: dict) -> dict:
    """Client-facing summary of session progress (no shoe contents or count exposed)."""
    return {
        'num_decks':           state['num_decks'],
        'num_hands':            state['num_hands'],
        'penetration':          state['penetration'],
        'dealer_hits_soft17':   state['dealer_hits_soft17'],
        'double_after_split':   state['double_after_split'],
        'live_mode':            state['live_mode'],
        'rounds_played':        state['rounds_played'],
        'hands_played':         state['hands_played'],
        'correct_decisions':    state['correct_decisions'],
        'total_decisions':      state['total_decisions'],
        'wins':                 state['wins'],
        'losses':               state['losses'],
        'pushes':               state['pushes'],
        'hint_used_count':      state['hint_used_count'],
        'done':                 state['done'],
        'round':                public_round_view(state['current_round']),
    }
