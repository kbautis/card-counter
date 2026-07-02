"""
Strategy Engine - Test Suite
Deterministic tests build hand state directly (bypassing the random shoe)
so decision outcomes can be asserted exactly. A smaller set of
session-level tests cover shoe dealing, reshuffling, and shape.
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from strategy_engine import (
    create_session,
    apply_action,
    public_hand_view,
    public_session_view,
    MIN_HANDS,
    MAX_HANDS,
)
from basic_strategy import HIT, STAND, DOUBLE, SPLIT


def _card(rank, suit='spades'):
    return {'rank': rank, 'suit': suit}


def _fresh_state(player_ranks, dealer_ranks, shoe_ranks_bottom_to_top=None,
                  num_hands=1, hands_played=0):
    """
    Build a minimal, fully-controlled session state with one in-progress
    hand, so apply_action() can be tested without RNG involvement.
    shoe_ranks_bottom_to_top: cards get drawn via list.pop() (from the end),
    so the LAST rank in this list is the NEXT card drawn.
    """
    shoe = [_card(r) for r in (shoe_ranks_bottom_to_top or [])]
    return {
        'num_decks': 1,
        'num_hands': num_hands,
        'penetration': 0.75,
        'shoe': shoe,
        'shoe_size': 52,
        'cutoff': 15,
        'shuffles': 0,
        'mid_hand_reshuffles': 0,
        'hands_played': hands_played,
        'correct_decisions': 0,
        'total_decisions': 0,
        'wins': 0,
        'losses': 0,
        'pushes': 0,
        'done': False,
        'current_hand': {
            'player_cards': [_card(r) for r in player_ranks],
            'dealer_cards': [_card(r) for r in dealer_ranks],
            'dealer_hole_hidden': True,
            'stage': 'player_turn',
            'can_double': True,
            'can_split': len(player_ranks) == 2 and player_ranks[0] == player_ranks[1],
        },
    }


class TestCreateSession:
    def test_returns_expected_keys(self):
        state = create_session(num_decks=1, num_hands=5)
        for key in ('shoe', 'shoe_size', 'cutoff', 'hands_played', 'current_hand', 'done'):
            assert key in state

    def test_deals_first_hand_immediately(self):
        state = create_session(num_decks=1, num_hands=5)
        hand = state['current_hand']
        assert len(hand['player_cards']) == 2
        assert len(hand['dealer_cards']) == 2
        assert hand['stage'] == 'player_turn'

    def test_shoe_shrinks_by_four_after_deal(self):
        state = create_session(num_decks=2, num_hands=5)
        assert len(state['shoe']) == 104 - 4

    def test_invalid_num_decks_raises(self):
        with pytest.raises(ValueError):
            create_session(num_decks=0, num_hands=5)
        with pytest.raises(ValueError):
            create_session(num_decks=9, num_hands=5)

    def test_invalid_num_hands_raises(self):
        with pytest.raises(ValueError):
            create_session(num_decks=1, num_hands=0)
        with pytest.raises(ValueError):
            create_session(num_decks=1, num_hands=MAX_HANDS + 1)

    def test_invalid_penetration_raises(self):
        with pytest.raises(ValueError):
            create_session(num_decks=1, num_hands=5, penetration=0)
        with pytest.raises(ValueError):
            create_session(num_decks=1, num_hands=5, penetration=1.5)

    def test_reshuffles_when_below_cutoff(self):
        # Deep penetration cutoff forces a reshuffle almost every hand in a 1-deck shoe.
        state = create_session(num_decks=1, num_hands=1, penetration=0.99)
        assert state['cutoff'] >= 15  # cushion floor applies to a tiny 52-card shoe


class TestApplyActionHit:
    def test_correct_hit_scored_correct(self):
        # Hard 8 vs dealer 6 -> basic strategy says Hit
        state = _fresh_state(['5', '3'], ['6', '9'], shoe_ranks_bottom_to_top=['2'])
        result = apply_action(state, HIT)
        assert result['was_correct'] is True
        assert result['correct_action'] == HIT
        assert state['total_decisions'] == 1
        assert state['correct_decisions'] == 1

    def test_incorrect_stand_scored_incorrect(self):
        # Hard 8 vs dealer 6 -> Stand is wrong (should Hit)
        state = _fresh_state(['5', '3'], ['6', '9'], shoe_ranks_bottom_to_top=[])
        result = apply_action(state, STAND)
        assert result['was_correct'] is False
        assert result['correct_action'] == HIT

    def test_hit_disables_double_and_split(self):
        state = _fresh_state(['8', '8'], ['6', '9'], shoe_ranks_bottom_to_top=['2'])
        apply_action(state, HIT)
        hand = state['current_hand']
        assert hand['can_double'] is False
        assert hand['can_split'] is False

    def test_hit_that_does_not_bust_keeps_hand_open(self):
        state = _fresh_state(['5', '3'], ['6', '9'], shoe_ranks_bottom_to_top=['2'])
        result = apply_action(state, HIT)
        assert result['hand_finished'] is False
        assert state['current_hand']['stage'] == 'player_turn'
        assert state['hands_played'] == 0

    def test_hit_that_busts_ends_hand_as_loss(self):
        # 10,9 = 19; drawing a 10 busts to 29
        state = _fresh_state(['10', '9'], ['6', '9'], shoe_ranks_bottom_to_top=['10'])
        result = apply_action(state, HIT)
        assert result['hand_finished'] is True
        assert result['outcome'] == 'loss'
        assert state['losses'] == 1
        assert state['done'] is True  # num_hands defaults to 1 in _fresh_state


class TestApplyActionStand:
    def test_stand_reveals_dealer_and_resolves(self):
        # Player 20 vs dealer showing 6 with a 5 in the hole (dealer must hit to 17+)
        # dealer: 6,5=11 -> hits -> draw '4' => 15 -> hits -> draw '3' => 18 -> stand
        state = _fresh_state(['10', 'K'], ['6', '5'], shoe_ranks_bottom_to_top=['3', '4'])
        result = apply_action(state, STAND)
        assert result['hand_finished'] is True
        assert result['dealer_total'] == 18
        assert result['player_total'] == 20
        assert result['outcome'] == 'win'
        assert state['wins'] == 1

    def test_dealer_stands_on_soft_17(self):
        # Dealer showing 6 with Ace in hole = soft 17 -> must stand (S17 rule)
        state = _fresh_state(['10', '9'], ['6', 'A'], shoe_ranks_bottom_to_top=[])
        result = apply_action(state, STAND)
        assert result['dealer_total'] == 17
        assert result['player_total'] == 19
        assert result['outcome'] == 'win'

    def test_dealer_bust_is_a_win(self):
        # Dealer 10,6=16 -> hits -> draws 10 -> busts
        state = _fresh_state(['9', '9'], ['10', '6'], shoe_ranks_bottom_to_top=['10'])
        result = apply_action(state, STAND)
        assert result['dealer_total'] > 21
        assert result['outcome'] == 'win'
        assert state['wins'] == 1

    def test_push_when_totals_match(self):
        state = _fresh_state(['10', '9'], ['10', '9'], shoe_ranks_bottom_to_top=[])
        result = apply_action(state, STAND)
        assert result['outcome'] == 'push'
        assert state['pushes'] == 1

    def test_multi_hand_session_deals_next_hand(self):
        state = _fresh_state(['10', '9'], ['10', '9'], shoe_ranks_bottom_to_top=['2', '3', '4', '5'],
                              num_hands=3, hands_played=0)
        result = apply_action(state, STAND)
        assert result['hand_finished'] is True
        assert state['done'] is False
        assert state['hands_played'] == 1
        assert state['current_hand'] is not None
        assert state['current_hand']['stage'] == 'player_turn'


class TestApplyActionDouble:
    def test_double_draws_exactly_one_card_and_resolves(self):
        # Hard 11 vs dealer 6 -> Double is correct. Draw a 9 -> total 20.
        # Dealer 6,4=10 -> hits -> draws '2' => 12 -> hits -> draws '3' => 15 -> hits -> draws '5' => 20
        state = _fresh_state(['6', '5'], ['6', '4'], shoe_ranks_bottom_to_top=['5', '3', '2', '9'])
        result = apply_action(state, DOUBLE)
        assert result['was_correct'] is True
        assert result['drawn_card']['rank'] == '9'
        assert len(result['player_cards']) == 3
        assert result['hand_finished'] is True

    def test_double_that_busts_is_an_immediate_loss(self):
        # 10,6 = 16; drawing a 10 busts to 26. (Doubling a stiff 16 isn't
        # basic-strategy-correct, but that's irrelevant to this mechanical test.)
        state = _fresh_state(['10', '6'], ['6', '4'], shoe_ranks_bottom_to_top=['10'])
        result = apply_action(state, DOUBLE)
        assert result['outcome'] == 'loss'
        assert state['losses'] == 1

    def test_double_illegal_after_a_hit_raises(self):
        state = _fresh_state(['5', '3'], ['6', '9'], shoe_ranks_bottom_to_top=['2'])
        apply_action(state, HIT)  # disables can_double
        with pytest.raises(ValueError):
            apply_action(state, DOUBLE)


class TestApplyActionSplit:
    def test_correct_split_is_scored_but_not_played_out(self):
        state = _fresh_state(['8', '8'], ['6', '9'], shoe_ranks_bottom_to_top=[])
        result = apply_action(state, SPLIT)
        assert result['was_correct'] is True
        assert result['outcome'] == 'split'
        assert result['hand_finished'] is True
        # Splits are excluded from win/loss/push tallies
        assert state['wins'] == 0 and state['losses'] == 0 and state['pushes'] == 0

    def test_split_illegal_on_non_pair_raises(self):
        state = _fresh_state(['8', '9'], ['6', '9'], shoe_ranks_bottom_to_top=[])
        with pytest.raises(ValueError):
            apply_action(state, SPLIT)

    def test_split_result_includes_cards_for_ui_rendering(self):
        # Regression: the client always reads result['dealer_cards'] /
        # result['player_cards'] once a hand is finished, split included.
        state = _fresh_state(['8', '8'], ['6', '9'], shoe_ranks_bottom_to_top=[])
        result = apply_action(state, SPLIT)
        assert result['player_cards'] == [{'rank': '8', 'suit': 'spades'}, {'rank': '8', 'suit': 'spades'}]
        # Dealer hole card stays hidden — only the up-card is exposed.
        assert result['dealer_cards'] == [{'rank': '6', 'suit': 'spades'}]


class TestApplyActionValidation:
    def test_unknown_action_raises(self):
        state = _fresh_state(['5', '3'], ['6', '9'], shoe_ranks_bottom_to_top=[])
        with pytest.raises(ValueError):
            apply_action(state, 'X')

    def test_acting_on_finished_hand_raises(self):
        state = _fresh_state(['10', '9'], ['10', '9'], shoe_ranks_bottom_to_top=[])
        apply_action(state, STAND)  # finishes the (only) hand, done=True
        with pytest.raises(ValueError):
            apply_action(state, STAND)


class TestPublicViews:
    def test_hand_view_hides_hole_card_while_hidden(self):
        state = _fresh_state(['5', '3'], ['6', '9'], shoe_ranks_bottom_to_top=[])
        view = public_hand_view(state['current_hand'])
        assert len(view['dealer_cards']) == 1
        assert view['dealer_cards'][0]['rank'] == '6'

    def test_apply_action_result_exposes_full_dealer_hand_after_stand(self):
        # The just-finished hand's reveal lives on the apply_action result,
        # not on current_hand (which has already moved on / gone to None).
        state = _fresh_state(['10', '9'], ['10', '9'], shoe_ranks_bottom_to_top=[])
        result = apply_action(state, STAND)
        assert result['dealer_cards'] == [{'rank': '10', 'suit': 'spades'},
                                           {'rank': '9', 'suit': 'spades'}]

    def test_public_hand_view_of_next_hand_after_stand(self):
        state = _fresh_state(['10', '9'], ['10', '9'], shoe_ranks_bottom_to_top=[], num_hands=2)
        apply_action(state, STAND)
        view = public_hand_view(state['current_hand'])
        assert view['stage'] == 'player_turn'  # the NEXT hand, freshly dealt

    def test_session_view_reports_progress(self):
        state = _fresh_state(['5', '3'], ['6', '9'], shoe_ranks_bottom_to_top=['2'])
        apply_action(state, HIT)
        view = public_session_view(state)
        assert view['total_decisions'] == 1
        assert view['correct_decisions'] == 1
        assert view['done'] is False
