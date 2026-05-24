"""
Card Counter - Test Suite
Tests cover all public functions in card_engine.py.
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from card_engine import (
    generate_shoe,
    hi_lo_value,
    calculate_count,
    calculate_true_count,
    create_session,
    verify_answer,
    MIN_CARDS,
)


# ── generate_shoe ────────────────────────────────────────────────────────────

class TestGenerateShoe:
    def test_single_deck_has_52_cards(self):
        shoe = generate_shoe(1)
        assert len(shoe) == 52

    def test_two_deck_shoe_has_104_cards(self):
        shoe = generate_shoe(2)
        assert len(shoe) == 104

    def test_six_deck_shoe_has_312_cards(self):
        shoe = generate_shoe(6)
        assert len(shoe) == 312

    def test_each_card_has_rank_and_suit(self):
        shoe = generate_shoe(1)
        for card in shoe:
            assert 'rank' in card
            assert 'suit' in card

    def test_single_deck_has_correct_rank_distribution(self):
        shoe = generate_shoe(1)
        ranks = [c['rank'] for c in shoe]
        for rank in ['2','3','4','5','6','7','8','9','10','J','Q','K','A']:
            assert ranks.count(rank) == 4  # one per suit

    def test_shoe_is_shuffled(self):
        # Two shoes should rarely be identical — not a guaranteed test
        # but a strong signal. Probability of collision is astronomically low.
        shoe1 = generate_shoe(1)
        shoe2 = generate_shoe(1)
        assert [c['rank'] for c in shoe1] != [c['rank'] for c in shoe2]

    def test_invalid_deck_count_raises(self):
        with pytest.raises(ValueError):
            generate_shoe(0)
        with pytest.raises(ValueError):
            generate_shoe(-1)
        with pytest.raises(ValueError):
            generate_shoe(9)  # max 8 decks


# ── hi_lo_value ──────────────────────────────────────────────────────────────

class TestHiLoValue:
    def test_low_cards_are_plus_one(self):
        for rank in ['2', '3', '4', '5', '6']:
            assert hi_lo_value({'rank': rank, 'suit': 'hearts'}) == +1

    def test_neutral_cards_are_zero(self):
        for rank in ['7', '8', '9']:
            assert hi_lo_value({'rank': rank, 'suit': 'hearts'}) == 0

    def test_high_cards_are_minus_one(self):
        for rank in ['10', 'J', 'Q', 'K', 'A']:
            assert hi_lo_value({'rank': rank, 'suit': 'hearts'}) == -1

    def test_unknown_rank_raises(self):
        with pytest.raises(ValueError):
            hi_lo_value({'rank': 'X', 'suit': 'hearts'})


# ── calculate_count ──────────────────────────────────────────────────────────

class TestCalculateCount:
    def test_empty_list_returns_zero(self):
        assert calculate_count([]) == 0

    def test_all_low_cards_count_up(self):
        cards = [{'rank': '2', 'suit': 'hearts'}] * 5
        assert calculate_count(cards) == 5

    def test_all_high_cards_count_down(self):
        cards = [{'rank': 'A', 'suit': 'spades'}] * 5
        assert calculate_count(cards) == -5

    def test_balanced_deck_counts_to_zero(self):
        # A complete single deck always sums to 0 in Hi-Lo
        shoe = generate_shoe(1)
        assert calculate_count(shoe) == 0

    def test_mixed_deck_correct_sum(self):
        cards = [
            {'rank': '2', 'suit': 'hearts'},    # +1
            {'rank': 'A', 'suit': 'spades'},    # -1
            {'rank': '5', 'suit': 'clubs'},     # +1
            {'rank': 'K', 'suit': 'diamonds'},  # -1
            {'rank': '7', 'suit': 'hearts'},    # 0
        ]
        assert calculate_count(cards) == 0


# ── calculate_true_count ─────────────────────────────────────────────────────

class TestCalculateTrueCount:
    def test_basic_true_count(self):
        # 2 decks dealt from a 4-deck shoe → 2 decks remain
        # running count +4 → true count = 4 / 2 = 2.0
        result = calculate_true_count(
            running_count=4,
            total_shoe_cards=208,  # 4 decks × 52
            cards_dealt=104,       # 2 decks dealt
        )
        assert result == pytest.approx(2.0)

    def test_partial_shoe_true_count(self):
        # 52 cards dealt from a 6-deck shoe (312 cards) → 260 remain (5 decks)
        # running count +10 → true count = 10 / 5 = 2.0
        result = calculate_true_count(
            running_count=10,
            total_shoe_cards=312,
            cards_dealt=52,
        )
        assert result == pytest.approx(2.0)

    def test_negative_running_count(self):
        # −6 running count with 3 decks remaining → true count = −2.0
        result = calculate_true_count(
            running_count=-6,
            total_shoe_cards=208,
            cards_dealt=52,  # 1 deck dealt, 3 remain
        )
        assert result == pytest.approx(-2.0)

    def test_zero_running_count(self):
        result = calculate_true_count(
            running_count=0,
            total_shoe_cards=104,
            cards_dealt=52,
        )
        assert result == pytest.approx(0.0)

    def test_full_shoe_dealt_returns_none(self):
        # No cards remain → true count is undefined
        result = calculate_true_count(
            running_count=5,
            total_shoe_cards=52,
            cards_dealt=52,
        )
        assert result is None

    def test_cards_dealt_beyond_shoe_returns_none(self):
        result = calculate_true_count(
            running_count=3,
            total_shoe_cards=52,
            cards_dealt=60,  # impossible but should not raise
        )
        assert result is None


# ── create_session ───────────────────────────────────────────────────────────

class TestCreateSession:
    def test_session_contains_required_keys(self):
        sess = create_session(num_decks=1, interval_ms=1000)
        for key in ('cards', 'hi_lo_values', 'correct_count', 'num_decks',
                    'interval_ms', 'total_shoe_size', 'cards_dealt'):
            assert key in sess, f"Missing key: {key}"

    def test_session_cards_match_deck_size(self):
        sess = create_session(num_decks=2, interval_ms=1500)
        assert len(sess['cards']) == 104

    def test_session_correct_count_is_integer(self):
        sess = create_session(num_decks=1, interval_ms=1000)
        assert isinstance(sess['correct_count'], int)

    def test_hi_lo_values_length_matches_cards(self):
        sess = create_session(num_decks=2, interval_ms=1000)
        assert len(sess['hi_lo_values']) == len(sess['cards'])

    def test_hi_lo_values_are_valid(self):
        sess = create_session(num_decks=1, interval_ms=1000)
        assert all(v in (-1, 0, 1) for v in sess['hi_lo_values'])

    def test_hi_lo_values_sum_matches_correct_count(self):
        sess = create_session(num_decks=1, interval_ms=1000)
        assert sum(sess['hi_lo_values']) == sess['correct_count']

    def test_total_shoe_size_is_full_shoe(self):
        sess = create_session(num_decks=3, interval_ms=1000)
        assert sess['total_shoe_size'] == 3 * 52

    def test_invalid_interval_raises(self):
        with pytest.raises(ValueError):
            create_session(num_decks=1, interval_ms=0)
        with pytest.raises(ValueError):
            create_session(num_decks=1, interval_ms=-500)

    # ── num_cards (partial shoe) ──────────────────────────────────────────────

    def test_partial_shoe_has_correct_card_count(self):
        sess = create_session(num_decks=2, interval_ms=1000, num_cards=30)
        assert len(sess['cards']) == 30
        assert sess['cards_dealt'] == 30

    def test_partial_shoe_total_size_is_full_shoe(self):
        sess = create_session(num_decks=2, interval_ms=1000, num_cards=30)
        assert sess['total_shoe_size'] == 104  # 2 decks, regardless of num_cards

    def test_partial_shoe_count_matches_dealt_cards(self):
        sess = create_session(num_decks=1, interval_ms=1000, num_cards=10)
        assert sess['correct_count'] == sum(sess['hi_lo_values'])
        assert len(sess['hi_lo_values']) == 10

    def test_full_num_cards_equals_full_shoe(self):
        sess = create_session(num_decks=1, interval_ms=1000, num_cards=52)
        assert sess['cards_dealt'] == 52
        assert sess['total_shoe_size'] == 52

    def test_num_cards_zero_raises(self):
        with pytest.raises(ValueError):
            create_session(num_decks=1, interval_ms=1000, num_cards=0)

    def test_num_cards_below_minimum_raises(self):
        with pytest.raises(ValueError):
            create_session(num_decks=1, interval_ms=1000, num_cards=MIN_CARDS - 1)

    def test_num_cards_exceeds_shoe_raises(self):
        with pytest.raises(ValueError):
            create_session(num_decks=1, interval_ms=1000, num_cards=53)

    def test_num_cards_none_gives_full_shoe(self):
        sess = create_session(num_decks=1, interval_ms=1000, num_cards=None)
        assert sess['cards_dealt'] == 52


# ── verify_answer ─────────────────────────────────────────────────────────────

class TestVerifyAnswer:
    def test_correct_answer_returns_correct_true(self):
        result = verify_answer(correct_count=5, user_count=5)
        assert result['correct'] is True

    def test_wrong_answer_returns_correct_false(self):
        result = verify_answer(correct_count=5, user_count=3)
        assert result['correct'] is False

    def test_result_contains_correct_count(self):
        result = verify_answer(correct_count=-3, user_count=0)
        assert result['correct_count'] == -3

    def test_result_contains_user_count(self):
        result = verify_answer(correct_count=5, user_count=2)
        assert result['user_count'] == 2

    def test_result_contains_delta(self):
        result = verify_answer(correct_count=5, user_count=3)
        assert result['delta'] == 2  # abs(5 - 3)

    def test_delta_is_always_non_negative(self):
        result = verify_answer(correct_count=3, user_count=5)
        assert result['delta'] == 2  # abs(3 - 5) = 2
