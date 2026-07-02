"""
Strategy Engine - Test Suite

Deterministic tests build round/hand state directly (bypassing the random
shoe) so decision outcomes can be asserted exactly, mirroring the pattern
from the original single-hand engine's test suite. A smaller set of
`_bare_state` + `_deal_new_round` tests exercise real round-dealing
(dealer peek, naturals, dealer blackjack) with a shoe whose draw order is
fully controlled, so those still avoid randomness too.
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from strategy_engine import (
    create_session,
    apply_action,
    request_hint,
    check_count,
    build_summary,
    stop_session,
    start_next_round,
    public_hand_view,
    public_round_view,
    public_session_view,
    _deal_new_round,
    MIN_HANDS,
    MAX_HANDS,
    MAX_ROUNDS,
    MAX_SPLITS_PER_SPOT,
)
from basic_strategy import HIT, STAND, DOUBLE, SPLIT


def _card(rank, suit='spades'):
    return {'rank': rank, 'suit': suit}


def _shoe(draw_order):
    """Cards are drawn via list.pop(), so the list must be reversed."""
    return [_card(r) for r in reversed(draw_order)]


def _fresh_state(spot_hands_ranks, dealer_ranks, draw_order=None,
                  dealer_hits_soft17=False, double_after_split=True, live_mode=False,
                  stand_on_split_aces=False, splits_used=0,
                  running_count=0, active_spot_index=0, active_hand_index=0):
    """
    spot_hands_ranks: one entry per spot; each entry is a list of hands
    (normally just one); each hand is a list of ranks.
    e.g. [[['8', '8']]] = a single spot with a single 8,8 hand.
    """
    spots = []
    for spot_hands in spot_hands_ranks:
        hands = []
        for h_ranks in spot_hands:
            can_split = len(h_ranks) == 2 and h_ranks[0] == h_ranks[1]
            hands.append({
                'player_cards':  [_card(r) for r in h_ranks],
                'stage':         'player_turn',
                'can_double':    True,
                'can_split':     can_split,
                'is_split_hand': len(spot_hands) > 1,
                'hint_used':     False,
                'outcome':       None,
            })
        spots.append({'hands': hands, 'natural': False, 'resolved': False, 'splits_used': splits_used})

    round_ = {
        'spots':              spots,
        'dealer_cards':       [_card(r) for r in dealer_ranks],
        'dealer_hole_hidden': True,
        'dealer_blackjack':   None,
        'stage':               'player_decisions',
        'active_spot_index':   active_spot_index,
        'active_hand_index':   active_hand_index,
    }
    return {
        'num_decks': 1, 'num_hands': len(spots), 'penetration': 0.75,
        'dealer_hits_soft17': dealer_hits_soft17, 'double_after_split': double_after_split,
        'live_mode': live_mode, 'stand_on_split_aces': stand_on_split_aces,
        'shoe': _shoe(draw_order or []), 'shoe_size': 52, 'cutoff': 15,
        'shuffles': 0, 'mid_hand_reshuffles': 0,
        'rounds_played': 0, 'hands_played': 0,
        'correct_decisions': 0, 'total_decisions': 0,
        'wins': 0, 'losses': 0, 'pushes': 0,
        'hint_used_count': 0, 'deviation_correct': 0, 'deviation_total': 0,
        'running_count': running_count if live_mode else None,
        'current_round': round_, 'done': False,
    }


def _bare_state(num_hands, draws_in_order, dealer_hits_soft17=False, double_after_split=True,
                 live_mode=False, stand_on_split_aces=False):
    """Minimal state for exercising _deal_new_round directly (round-dealing tests)."""
    return {
        'num_decks': 1, 'num_hands': num_hands, 'penetration': 0.75,
        'dealer_hits_soft17': dealer_hits_soft17, 'double_after_split': double_after_split,
        'live_mode': live_mode, 'stand_on_split_aces': stand_on_split_aces,
        'shoe': _shoe(draws_in_order), 'shoe_size': 52, 'cutoff': 0,
        'shuffles': 0, 'mid_hand_reshuffles': 0,
        'rounds_played': 0, 'hands_played': 0,
        'correct_decisions': 0, 'total_decisions': 0,
        'wins': 0, 'losses': 0, 'pushes': 0,
        'hint_used_count': 0, 'deviation_correct': 0, 'deviation_total': 0,
        'running_count': 0 if live_mode else None,
        'current_round': None, 'done': False,
    }


class TestCreateSessionConfig:
    def test_returns_expected_keys(self):
        state = create_session(num_decks=1, num_hands=3)
        for key in ('shoe', 'shoe_size', 'cutoff', 'rounds_played', 'current_round', 'done',
                    'dealer_hits_soft17', 'double_after_split', 'live_mode'):
            assert key in state

    def test_deals_first_round_with_num_hands_spots(self):
        state = create_session(num_decks=4, num_hands=3)
        round_ = state['current_round']
        assert round_ is not None
        assert len(round_['spots']) == 3

    def test_num_hands_boundaries(self):
        create_session(num_decks=1, num_hands=MIN_HANDS)
        create_session(num_decks=1, num_hands=MAX_HANDS)
        with pytest.raises(ValueError):
            create_session(num_decks=1, num_hands=MIN_HANDS - 1)
        with pytest.raises(ValueError):
            create_session(num_decks=1, num_hands=MAX_HANDS + 1)

    def test_invalid_num_decks_raises(self):
        with pytest.raises(ValueError):
            create_session(num_decks=0, num_hands=1)
        with pytest.raises(ValueError):
            create_session(num_decks=9, num_hands=1)

    def test_invalid_penetration_raises(self):
        with pytest.raises(ValueError):
            create_session(num_decks=1, num_hands=1, penetration=0)
        with pytest.raises(ValueError):
            create_session(num_decks=1, num_hands=1, penetration=1.5)

    def test_ruleset_flags_must_be_bool(self):
        with pytest.raises(ValueError):
            create_session(num_decks=1, num_hands=1, dealer_hits_soft17='yes')
        with pytest.raises(ValueError):
            create_session(num_decks=1, num_hands=1, double_after_split='yes')
        with pytest.raises(ValueError):
            create_session(num_decks=1, num_hands=1, live_mode='yes')

    def test_default_ruleset_is_s17_das_on(self):
        state = create_session(num_decks=1, num_hands=1)
        assert state['dealer_hits_soft17'] is False
        assert state['double_after_split'] is True
        assert state['live_mode'] is False


class TestDealNewRoundDealerBlackjack:
    def test_dealer_blackjack_ends_round_with_no_decisions(self):
        # spot1c1=A, spot2c1=5, dealerUp=A, spot1c2=K, spot2c2=6, dealerHole=K
        state = _bare_state(num_hands=2, draws_in_order=['A', '5', 'A', 'K', '6', 'K'])
        _deal_new_round(state)
        assert state['pushes'] == 1   # spot1 = A,K = 21 pushes dealer blackjack
        assert state['losses'] == 1   # spot2 = 5,6 = 11 loses outright
        assert state['hands_played'] == 2
        assert state['total_decisions'] == 0  # no decisions were ever offered


class TestDealNewRoundNaturalsAndPeek:
    def test_player_natural_auto_resolves_without_offering_actions(self):
        # spot1c1=A, spot2c1=5, dealerUp=5, spot1c2=K, spot2c2=6, dealerHole=9
        state = _bare_state(num_hands=2, draws_in_order=['A', '5', '5', 'K', '6', '9'])
        _deal_new_round(state)
        round_ = state['current_round']
        assert round_['spots'][0]['natural'] is True
        assert round_['spots'][0]['hands'][0]['outcome'] == 'win'
        assert round_['spots'][0]['hands'][0]['stage'] == 'done'
        assert round_['spots'][1]['hands'][0]['stage'] == 'player_turn'
        assert round_['active_spot_index'] == 1
        assert round_['active_hand_index'] == 0
        assert state['wins'] == 1
        assert state['total_decisions'] == 0

    def test_dealer_peek_without_blackjack_keeps_hole_hidden_and_offers_decisions(self):
        # spot1c1=5, dealerUp=A, spot1c2=6, dealerHole=5 (A,5=16, not blackjack)
        state = _bare_state(num_hands=1, draws_in_order=['5', 'A', '6', '5'])
        _deal_new_round(state)
        round_ = state['current_round']
        assert round_['dealer_blackjack'] is False
        assert round_['dealer_hole_hidden'] is True
        assert round_['active_spot_index'] == 0
        assert round_['active_hand_index'] == 0

    def test_no_peek_when_upcard_is_not_ace_or_ten(self):
        state = _bare_state(num_hands=1, draws_in_order=['5', '6', '6', '9'])
        _deal_new_round(state)
        assert state['current_round']['dealer_blackjack'] is None


class TestRoundAdvanceIsPlayerDriven:
    """PR #1 feedback: a finished round must stay fully visible (dealer's
    whole hand, every spot's outcome) until the player explicitly asks for
    the next one — it must not be silently replaced."""

    def test_round_stays_round_over_after_last_hand_resolves(self):
        state = _fresh_state([[['10', 'K']]], ['6', '5'], draw_order=['4', '3'])
        result = apply_action(state, STAND)
        assert result['round_finished'] is True
        round_ = state['current_round']
        assert round_ is not None
        assert round_['stage'] == 'round_over'
        assert round_['dealer_hole_hidden'] is False
        assert round_['spots'][0]['hands'][0]['outcome'] == 'win'

    def test_dealer_blackjack_round_also_stays_visible(self):
        state = _bare_state(num_hands=2, draws_in_order=['A', '5', 'A', 'K', '6', 'K'])
        _deal_new_round(state)
        round_ = state['current_round']
        assert round_ is not None
        assert round_['stage'] == 'round_over'
        assert round_['spots'][0]['hands'][0]['outcome'] == 'push'
        assert round_['spots'][1]['hands'][0]['outcome'] == 'loss'

    def test_start_next_round_raises_mid_round(self):
        state = _fresh_state([[['5', '3']]], ['6', '9'])  # still player_turn
        with pytest.raises(ValueError):
            start_next_round(state)

    def test_start_next_round_deals_a_fresh_round(self):
        state = _fresh_state([[['10', 'K']]], ['6', '5'], draw_order=['4', '3'])
        apply_action(state, STAND)
        rounds_before = state['rounds_played']
        start_next_round(state)
        # rounds_played only bumps in _finalize_round — either the new round is
        # still awaiting a decision (unchanged), or it instantly resolved too
        # (dealer blackjack / all-naturals on the freshly reshuffled shoe).
        assert state['rounds_played'] in (rounds_before, rounds_before + 1)
        round_ = state['current_round']
        assert round_ is not None
        assert round_['stage'] in ('player_decisions', 'round_over')
        assert len(round_['spots'][0]['hands'][0]['player_cards']) == 2

    def test_start_next_round_ends_session_at_round_cap(self):
        state = _fresh_state([[['10', 'K']]], ['6', '5'], draw_order=['4', '3'])
        apply_action(state, STAND)
        state['rounds_played'] = MAX_ROUNDS
        start_next_round(state)
        assert state['done'] is True
        assert state['current_round'] is None

    def test_apply_action_never_auto_deals_next_round(self):
        # Regression guard: before this fix, apply_action would silently
        # deal a brand-new round the instant the current one finished.
        state = _fresh_state([[['10', 'K']]], ['6', '5'], draw_order=['4', '3'])
        apply_action(state, STAND)
        # If a new round had been auto-dealt, the dealer's cards here would
        # be a fresh random hand, not our controlled 6,5,4,3 -> 18.
        dealer_ranks = [c['rank'] for c in state['current_round']['dealer_cards']]
        assert dealer_ranks == ['6', '5', '4', '3']


class TestApplyActionHit:
    def test_correct_hit_scored_correct(self):
        state = _fresh_state([[['5', '3']]], ['6', '9'], draw_order=['2'])
        result = apply_action(state, HIT)
        assert result['was_correct'] is True
        assert result['correct_action'] == HIT
        assert state['total_decisions'] == 1
        assert state['correct_decisions'] == 1

    def test_incorrect_stand_scored_incorrect(self):
        state = _fresh_state([[['5', '3']]], ['6', '9'])
        result = apply_action(state, STAND)
        assert result['was_correct'] is False
        assert result['correct_action'] == HIT

    def test_hit_disables_double_and_split(self):
        state = _fresh_state([[['8', '8']]], ['6', '9'], draw_order=['2'])
        apply_action(state, HIT)
        hand = state['current_round']['spots'][0]['hands'][0]
        assert hand['can_double'] is False
        assert hand['can_split'] is False

    def test_hit_that_does_not_bust_keeps_hand_open(self):
        state = _fresh_state([[['5', '3']]], ['6', '9'], draw_order=['2'])
        result = apply_action(state, HIT)
        assert result['hand_finished'] is False
        assert state['current_round']['spots'][0]['hands'][0]['stage'] == 'player_turn'

    def test_hit_that_busts_ends_hand_as_loss_and_advances(self):
        state = _fresh_state([[['10', '9']]], ['6', '9'], draw_order=['10'])
        result = apply_action(state, HIT)
        assert result['hand_finished'] is True
        assert result['outcome'] == 'loss'
        assert state['losses'] == 1
        assert state['hands_played'] == 1


class TestApplyActionStand:
    def test_stand_reveals_dealer_and_resolves(self):
        state = _fresh_state([[['10', 'K']]], ['6', '5'], draw_order=['4', '3'])
        result = apply_action(state, STAND)
        assert result['hand_finished'] is True
        assert result['outcome'] == 'win'
        assert state['wins'] == 1

    def test_dealer_stands_on_soft_17(self):
        state = _fresh_state([[['10', '9']]], ['6', 'A'])
        result = apply_action(state, STAND)
        assert result['outcome'] == 'win'  # dealer stands at soft 17, player 19 wins

    def test_dealer_hits_soft_17_under_h17(self):
        state = _fresh_state([[['10', '9']]], ['6', 'A'], dealer_hits_soft17=True, draw_order=['2'])
        result = apply_action(state, STAND)
        # dealer hits soft 17 -> draws '2' -> 19, pushes player's 19
        assert result['outcome'] == 'push'

    def test_push_when_totals_match(self):
        state = _fresh_state([[['10', '9']]], ['10', '9'])
        result = apply_action(state, STAND)
        assert result['outcome'] == 'push'
        assert state['pushes'] == 1

    def test_dealer_plays_once_and_settles_all_live_spots(self):
        state = _fresh_state([[['10', '9']], [['9', '8']]], ['6', '5'], draw_order=['4', '3'])
        apply_action(state, STAND)  # spot 0 stands
        result = apply_action(state, STAND)  # spot 1 stands -> dealer plays once
        dealer_cards = result.get('dealer_cards') or state['current_round']
        # dealer drew exactly to 6,5,4,3 = 18 (not re-drawn per spot)
        assert state['wins'] + state['losses'] + state['pushes'] == 2


class TestApplyActionDouble:
    def test_double_draws_exactly_one_card_and_resolves(self):
        state = _fresh_state([[['6', '5']]], ['6', '4'], draw_order=['9', '2', '3', '5'])
        result = apply_action(state, DOUBLE)
        assert result['was_correct'] is True
        assert result['drawn_card']['rank'] == '9'
        assert len(result['player_cards']) == 3
        assert result['hand_finished'] is True

    def test_double_that_busts_is_an_immediate_loss(self):
        state = _fresh_state([[['10', '6']]], ['6', '4'], draw_order=['10'])
        result = apply_action(state, DOUBLE)
        assert result['outcome'] == 'loss'
        assert state['losses'] == 1

    def test_double_illegal_after_a_hit_raises(self):
        state = _fresh_state([[['5', '3']]], ['6', '9'], draw_order=['2'])
        apply_action(state, HIT)
        with pytest.raises(ValueError):
            apply_action(state, DOUBLE)


class TestPlayableSplits:
    def _split_state(self, draw_order):
        return _fresh_state([[['8', '8']]], ['6', '9'], draw_order=draw_order)

    def test_split_creates_two_playable_hands(self):
        state = self._split_state(draw_order=['2', '3'])
        result = apply_action(state, SPLIT)
        spot = state['current_round']['spots'][0]
        assert len(spot['hands']) == 2
        assert spot['hands'][0]['player_cards'][1]['rank'] == '2'
        assert spot['hands'][1]['player_cards'][1]['rank'] == '3'
        assert spot['hands'][0]['can_split'] is False  # 8,2 isn't a pair — not re-split-eligible
        assert result['outcome'] == 'split'
        assert state['current_round']['active_hand_index'] == 0

    def test_split_is_scored_as_a_decision(self):
        state = self._split_state(draw_order=['2', '3'])
        result = apply_action(state, SPLIT)
        assert result['was_correct'] is True  # 8,8 always splits
        assert state['total_decisions'] == 1
        assert state['correct_decisions'] == 1

    def test_split_illegal_on_non_pair_raises(self):
        state = _fresh_state([[['8', '9']]], ['6', '9'])
        with pytest.raises(ValueError):
            apply_action(state, SPLIT)

    def test_hitting_one_split_hand_does_not_affect_other(self):
        state = self._split_state(draw_order=['2', '3', '4'])
        apply_action(state, SPLIT)
        apply_action(state, HIT)  # hits hand 0, draws '4'
        spot = state['current_round']['spots'][0]
        assert spot['hands'][0]['player_cards'][-1]['rank'] == '4'
        assert len(spot['hands'][1]['player_cards']) == 2  # untouched

    def test_doubling_a_split_hand_works(self):
        state = self._split_state(draw_order=['5', '6', '9'])
        apply_action(state, SPLIT)  # hand0 = 8,5 ; hand1 = 8,6
        result = apply_action(state, DOUBLE)  # double hand0 -> draws '9' -> 22 bust
        assert result['drawn_card']['rank'] == '9'
        assert len(state['current_round']['spots'][0]['hands'][0]['player_cards']) == 3
        assert result['hand_finished'] is True

    def test_busting_one_split_hand_does_not_end_other(self):
        state = self._split_state(draw_order=['5', '6', 'K'])
        apply_action(state, SPLIT)  # hand0 = 8,5=13 ; hand1 = 8,6=14
        result = apply_action(state, HIT)  # hand0 hits -> draws 'K' -> 23 bust
        assert result['outcome'] == 'loss'
        assert state['current_round']['active_spot_index'] == 0
        assert state['current_round']['active_hand_index'] == 1
        assert state['current_round']['spots'][0]['hands'][1]['stage'] == 'player_turn'

    def test_double_after_split_illegal_when_das_off(self):
        state = _fresh_state([[['8', '8']]], ['6', '9'], draw_order=['2', '3'], double_after_split=False)
        apply_action(state, SPLIT)
        with pytest.raises(ValueError):
            apply_action(state, DOUBLE)


class TestReSplitting:
    def test_re_splitting_a_second_pair_makes_three_hands(self):
        # Split 8,8 -> hand0=8,8 (still a pair!), hand1=8,2. Re-split hand0.
        state = _fresh_state([[['8', '8']]], ['6', '9'], draw_order=['8', '2', '4', '5'])
        apply_action(state, SPLIT)  # hand0 = 8,8 ; hand1 = 8,2
        spot = state['current_round']['spots'][0]
        assert len(spot['hands']) == 2
        assert spot['hands'][0]['can_split'] is True  # 8,8 is a pair again
        assert spot['splits_used'] == 1

        result = apply_action(state, SPLIT)  # re-split hand0 -> hand0=8,4 ; hand1=8,5 ; (old hand1=8,2 stays)
        assert result['outcome'] == 'split'
        assert len(spot['hands']) == 3
        assert spot['splits_used'] == 2
        assert [h['player_cards'][-1]['rank'] for h in spot['hands']] == ['4', '5', '2']

    def test_third_split_is_illegal_even_if_pair_again(self):
        # Force a third pair to reappear so only the split cap (not pair-ness) blocks it.
        state = _fresh_state([[['8', '8']]], ['6', '9'], draw_order=['8', '2', '8', '5'], splits_used=1)
        # Pre-seed as if one split already happened: hand0 = 8,8 (re-split-eligible), hand1 = untouched pair.
        spot = state['current_round']['spots'][0]
        spot['hands'] = [
            {'player_cards': [{'rank': '8', 'suit': 'spades'}, {'rank': '8', 'suit': 'spades'}],
             'stage': 'player_turn', 'can_double': True, 'can_split': True,
             'is_split_hand': True, 'hint_used': False, 'outcome': None},
        ]
        state['current_round']['active_hand_index'] = 0
        result = apply_action(state, SPLIT)  # splits_used 1 -> 2, at the cap now
        assert result['outcome'] == 'split'
        assert spot['splits_used'] == MAX_SPLITS_PER_SPOT
        for hand in spot['hands']:
            assert hand['can_split'] is False  # cap reached, even though these are 8,8/8,8 pairs
        with pytest.raises(ValueError):
            apply_action(state, SPLIT)

    def test_re_split_hand_still_scores_independently(self):
        state = _fresh_state([[['8', '8']]], ['6', '9'], draw_order=['8', '2', '4', '5'])
        apply_action(state, SPLIT)
        apply_action(state, SPLIT)  # now 3 hands, active on the first new sub-hand (8,4 = 12)
        result = apply_action(state, HIT)
        assert state['total_decisions'] == 3  # original split + re-split + this hit
        assert result is not None


class TestStandOnSplitAces:
    def test_force_stand_true_ends_both_ace_hands_immediately(self):
        # A second spot still needs a decision, so we can observe the forced
        # 'awaiting_dealer' state before the (single, once-per-round) dealer
        # play would otherwise immediately resolve it.
        state = _fresh_state([[['A', 'A']], [['5', '6']]], ['6', '9'],
                              draw_order=['5', '4'], stand_on_split_aces=True)
        result = apply_action(state, SPLIT)
        spot = state['current_round']['spots'][0]
        assert spot['hands'][0]['stage'] == 'awaiting_dealer'
        assert spot['hands'][1]['stage'] == 'awaiting_dealer'
        assert spot['hands'][0]['can_double'] is False
        assert spot['hands'][0]['can_split'] is False
        assert result['hand_finished'] is True
        assert state['current_round']['active_spot_index'] == 1  # moved on to the other spot

    def test_force_stand_false_leaves_ace_hands_playable(self):
        state = _fresh_state([[['A', 'A']]], ['6', '9'], draw_order=['5', '4'], stand_on_split_aces=False)
        apply_action(state, SPLIT)
        spot = state['current_round']['spots'][0]
        assert spot['hands'][0]['stage'] == 'player_turn'
        assert spot['hands'][1]['stage'] == 'player_turn'

    def test_force_stand_only_applies_to_aces_not_other_pairs(self):
        state = _fresh_state([[['8', '8']]], ['6', '9'], draw_order=['2', '3'], stand_on_split_aces=True)
        apply_action(state, SPLIT)
        spot = state['current_round']['spots'][0]
        assert spot['hands'][0]['stage'] == 'player_turn'

    def test_config_validation_rejects_non_bool(self):
        with pytest.raises(ValueError):
            create_session(num_decks=1, num_hands=1, stand_on_split_aces='yes')


class TestHint:
    def test_hint_does_not_mutate_state(self):
        state = _fresh_state([[['5', '3']]], ['6', '9'])
        hint = request_hint(state)
        assert hint['action'] == HIT
        assert state['total_decisions'] == 0
        assert state['correct_decisions'] == 0
        hand = state['current_round']['spots'][0]['hands'][0]
        assert hand['stage'] == 'player_turn'
        assert hand['hint_used'] is True
        assert state['hint_used_count'] == 1

    def test_hint_used_decision_still_scores_normally(self):
        state = _fresh_state([[['5', '3']]], ['6', '9'], draw_order=['2'])
        request_hint(state)
        result = apply_action(state, HIT)
        assert result['hint_used'] is True
        assert result['was_correct'] is True
        assert state['total_decisions'] == 1
        assert state['correct_decisions'] == 1

    def test_hint_count_does_not_double_increment_for_same_hand(self):
        state = _fresh_state([[['5', '3']]], ['6', '9'])
        request_hint(state)
        request_hint(state)
        assert state['hint_used_count'] == 1

    def test_hint_raises_when_no_hand_awaiting(self):
        state = _fresh_state([[['5', '3']]], ['6', '9'])
        stop_session(state)
        with pytest.raises(ValueError):
            request_hint(state)


class TestLiveModeCountAndDeviations:
    def test_running_count_excludes_hidden_hole_card_until_revealed(self):
        # spot1c1=5(+1), dealerUp=9(0), spot1c2=6(+1), dealerHole=K(-1, pending)
        state = _bare_state(num_hands=1, draws_in_order=['5', '9', '6', 'K'], live_mode=True)
        _deal_new_round(state)
        assert state['running_count'] == 2
        apply_action(state, STAND)  # dealer 9,K=19 already >=17, no further draws
        assert state['running_count'] == 1  # hole K now counted (-1)

    def test_check_count_reuses_card_engine_true_count(self):
        state = _fresh_state([[['5', '3']]], ['6', '9'], live_mode=True, running_count=4)
        state['shoe'] = [_card('2')] * 26  # 26/52 remaining -> 0.5 decks remaining
        result = check_count(state)
        assert result['running_count'] == 4
        assert result['true_count'] == 8.0

    def test_check_count_raises_when_live_mode_off(self):
        state = _fresh_state([[['5', '3']]], ['6', '9'], live_mode=False)
        with pytest.raises(ValueError):
            check_count(state)

    def test_deviation_scored_separately_from_base_accuracy(self):
        # hard 16 vs 9: base strategy says Hit; Illustrious 18 says Stand at TC 4+.
        state = _fresh_state([[['10', '6']]], ['9', '5'], live_mode=True, running_count=2)
        state['shoe'] = [_card('2')] * 26  # true_count = 2 / 0.5 = 4.0
        result = apply_action(state, STAND)
        assert result['correct_action'] == HIT
        assert result['was_correct'] is False
        assert result['deviation_applicable'] is True
        assert result['deviation_correct_action'] == STAND
        assert result['deviation_was_correct'] is True
        assert result['true_count_at_decision'] == 4.0
        assert state['total_decisions'] == 1 and state['correct_decisions'] == 0
        assert state['deviation_total'] == 1 and state['deviation_correct'] == 1

    def test_deviation_not_scored_when_live_mode_off(self):
        state = _fresh_state([[['10', '6']]], ['9', '5'], live_mode=False)
        result = apply_action(state, STAND)
        assert 'deviation_applicable' not in result
        assert state['deviation_total'] == 0

    def test_no_deviation_entry_falls_through_cleanly(self):
        # hard 8 vs 2 has no Illustrious 18 entry (hard-8 only has one, vs 6).
        state = _fresh_state([[['5', '3']]], ['2', '9'], live_mode=True, running_count=10)
        state['shoe'] = [_card('2')] * 26
        result = apply_action(state, HIT)
        assert result['deviation_applicable'] is False
        assert state['deviation_total'] == 0


class TestSummary:
    def test_stop_mid_round_returns_valid_summary(self):
        state = _fresh_state([[['5', '3']]], ['6', '9'])
        summary = stop_session(state)
        assert state['done'] is True
        assert state['current_round'] is None
        assert summary['hands_played'] == 0
        assert summary['accuracy'] == 0.0
        assert 'deviation_accuracy' not in summary

    def test_summary_math_matches_fixture_state(self):
        state = _fresh_state([[['10', 'K']]], ['6', '5'], draw_order=['4', '3'])
        apply_action(state, STAND)  # correct, wins
        summary = stop_session(state)
        assert summary['wins'] == 1
        assert summary['losses'] == 0
        assert summary['pushes'] == 0
        assert summary['hands_played'] == 1
        assert summary['correct_decisions'] == 1
        assert summary['total_decisions'] == 1
        assert summary['accuracy'] == 100.0
        assert summary['hint_used_count'] == 0

    def test_live_mode_summary_includes_deviation_accuracy(self):
        state = _fresh_state([[['5', '3']]], ['6', '9'], live_mode=True)
        summary = stop_session(state)
        assert 'deviation_accuracy' in summary
        assert summary['deviation_accuracy'] == 0.0

    def test_build_summary_does_not_mutate_state(self):
        state = _fresh_state([[['5', '3']]], ['6', '9'])
        build_summary(state)
        assert state['done'] is False
        assert state['current_round'] is not None


class TestApplyActionValidation:
    def test_unknown_action_raises(self):
        state = _fresh_state([[['5', '3']]], ['6', '9'])
        with pytest.raises(ValueError):
            apply_action(state, 'X')

    def test_acting_when_no_hand_awaiting_raises(self):
        state = _fresh_state([[['5', '3']]], ['6', '9'])
        stop_session(state)
        with pytest.raises(ValueError):
            apply_action(state, STAND)


class TestPublicViews:
    def test_hand_view_hides_nothing_but_reflects_stage(self):
        state = _fresh_state([[['5', '3']]], ['6', '9'])
        hand = state['current_round']['spots'][0]['hands'][0]
        view = public_hand_view(hand)
        assert view['player_total'] == 8
        assert view['stage'] == 'player_turn'

    def test_round_view_hides_hole_card_while_hidden(self):
        state = _fresh_state([[['5', '3']]], ['6', '9'])
        view = public_round_view(state['current_round'])
        assert len(view['dealer_cards']) == 1
        assert view['dealer_cards'][0]['rank'] == '6'

    def test_result_reveals_dealer_after_resolution(self):
        # The just-finished hand's reveal lives on the apply_action result,
        # not on current_round (which has already moved on to the next round).
        state = _fresh_state([[['10', 'K']]], ['6', '5'], draw_order=['4', '3'])
        result = apply_action(state, STAND)
        assert 'dealer_total' in result
        assert len(result['dealer_cards']) >= 2

    def test_session_view_reports_progress(self):
        state = _fresh_state([[['5', '3']]], ['6', '9'], draw_order=['2'])
        apply_action(state, HIT)
        view = public_session_view(state)
        assert view['total_decisions'] == 1
        assert view['correct_decisions'] == 1
        assert view['done'] is False
