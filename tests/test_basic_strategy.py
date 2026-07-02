"""
Basic Strategy - Test Suite
Tests cover hand_total, is_pair, and correct_action against well-known
basic strategy decision points across the H17/S17 x DAS/no-DAS matrix.
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from basic_strategy import (
    hand_total,
    is_pair,
    correct_action,
    action_name,
    HIT, STAND, DOUBLE, SPLIT,
)

# Baseline ruleset used by tests that aren't specifically exercising a
# H17/S17 or DAS divergence: S17, DAS on.
S17, H17 = False, True
DAS_ON, DAS_OFF = True, False


def _action(player_ranks, dealer_upcard, dealer_hits_soft17=S17, double_after_split=DAS_ON,
            can_double=True, can_split=True):
    return correct_action(
        player_ranks, dealer_upcard, dealer_hits_soft17, double_after_split,
        can_double=can_double, can_split=can_split,
    )


class TestHandTotal:
    def test_simple_hard_total(self):
        assert hand_total(['5', '7']) == (12, False)

    def test_ace_counted_as_soft_eleven(self):
        assert hand_total(['A', '6']) == (17, True)

    def test_ace_downgrades_to_avoid_bust(self):
        assert hand_total(['A', '9', '5']) == (15, False)

    def test_two_aces(self):
        # A,A = 12 soft (one ace as 11, one as 1)
        assert hand_total(['A', 'A']) == (12, True)

    def test_face_cards_count_as_ten(self):
        assert hand_total(['K', 'Q']) == (20, False)

    def test_empty_hand_raises(self):
        with pytest.raises(ValueError):
            hand_total([])

    def test_hard_21(self):
        assert hand_total(['7', '7', '7']) == (21, False)

    def test_bust(self):
        assert hand_total(['K', 'Q', '5']) == (25, False)


class TestIsPair:
    def test_matching_ranks_is_pair(self):
        assert is_pair(['8', '8']) is True

    def test_ten_value_cards_are_pair(self):
        assert is_pair(['10', 'K']) is True  # both worth 10

    def test_different_ranks_not_pair(self):
        assert is_pair(['8', '9']) is False

    def test_three_cards_never_a_pair(self):
        assert is_pair(['8', '8', '8']) is False


class TestActionName:
    def test_known_codes(self):
        assert action_name(HIT) == 'Hit'
        assert action_name(STAND) == 'Stand'
        assert action_name(DOUBLE) == 'Double'
        assert action_name(SPLIT) == 'Split'

    def test_unknown_code_raises(self):
        with pytest.raises(ValueError):
            action_name('X')


class TestCorrectActionHardTotals:
    def test_hard_8_always_hits(self):
        assert _action(['5', '3'], '6') == HIT

    def test_hard_11_doubles_vs_low_and_mid(self):
        assert _action(['6', '5'], '6') == DOUBLE
        assert _action(['6', '5'], '10') == DOUBLE

    def test_hard_11_vs_ace_hits_under_s17(self):
        assert _action(['6', '5'], 'A', dealer_hits_soft17=S17) == HIT

    def test_hard_11_vs_ace_doubles_under_h17(self):
        assert _action(['6', '5'], 'A', dealer_hits_soft17=H17) == DOUBLE

    def test_hard_12_stands_vs_4_5_6(self):
        assert _action(['7', '5'], '4') == STAND
        assert _action(['7', '5'], '6') == STAND

    def test_hard_12_hits_vs_2_3_and_7plus(self):
        assert _action(['7', '5'], '2') == HIT
        assert _action(['7', '5'], '7') == HIT

    def test_hard_16_stands_vs_6_hits_vs_10(self):
        assert _action(['10', '6'], '6') == STAND
        assert _action(['10', '6'], '10') == HIT

    def test_hard_17_always_stands(self):
        assert _action(['10', '7'], 'A') == STAND

    def test_double_downgrades_to_hit_when_illegal(self):
        # Hard 11 vs 6 wants Double, but if it's not the first move, Hit instead.
        assert _action(['6', '5'], '6', can_double=False) == HIT


class TestCorrectActionSoftTotals:
    def test_soft_18_stands_vs_2_under_s17(self):
        assert _action(['A', '7'], '2', dealer_hits_soft17=S17) == STAND

    def test_soft_18_doubles_vs_2_under_h17(self):
        # H17: A,7 vs 2 is Ds (double if allowed) — differs from S17 (plain stand)
        assert _action(['A', '7'], '2', dealer_hits_soft17=H17) == DOUBLE

    def test_soft_18_ds_falls_back_to_stand_when_double_illegal(self):
        assert _action(['A', '7'], '2', dealer_hits_soft17=H17, can_double=False) == STAND

    def test_soft_18_doubles_vs_4(self):
        assert _action(['A', '7'], '4') == DOUBLE

    def test_soft_18_hits_vs_9(self):
        assert _action(['A', '7'], '9') == HIT

    def test_soft_19_never_doubles_vs_6_under_s17(self):
        assert _action(['A', '8'], '6', dealer_hits_soft17=S17) == STAND

    def test_soft_19_doubles_vs_6_under_h17(self):
        assert _action(['A', '8'], '6', dealer_hits_soft17=H17) == DOUBLE

    def test_soft_13_hits_vs_2(self):
        assert _action(['A', '2'], '2') == HIT

    def test_soft_20_always_stands(self):
        assert _action(['A', '9'], '6') == STAND


class TestCorrectActionPairs:
    def test_aces_always_split(self):
        assert _action(['A', 'A'], '2') == SPLIT
        assert _action(['A', 'A'], 'A') == SPLIT

    def test_tens_never_split(self):
        assert _action(['10', 'K'], '6') == STAND

    def test_eights_always_split(self):
        assert _action(['8', '8'], 'A') == SPLIT

    def test_fives_treated_as_hard_ten(self):
        # 5,5 should never split — plays like a hard 10
        assert _action(['5', '5'], '6') == DOUBLE
        assert _action(['5', '5'], '10') == HIT

    def test_nines_split_vs_6_stand_vs_7(self):
        assert _action(['9', '9'], '6') == SPLIT
        assert _action(['9', '9'], '7') == STAND

    def test_split_downgrades_to_hit_when_illegal(self):
        assert _action(['8', '8'], 'A', can_split=False) == HIT

    def test_pair_check_skipped_when_split_illegal_and_totals_used(self):
        # 6,6 with split disallowed should fall back to hard-12 logic
        assert _action(['6', '6'], '5', can_split=False) == STAND


class TestCorrectActionValidation:
    def test_single_card_raises(self):
        with pytest.raises(ValueError):
            _action(['5'], '6')

    def test_unknown_dealer_upcard_raises(self):
        with pytest.raises(ValueError):
            _action(['5', '6'], 'X')

    def test_non_bool_dealer_hits_soft17_raises(self):
        with pytest.raises(ValueError):
            correct_action(['5', '6'], '6', dealer_hits_soft17='no', double_after_split=True)

    def test_non_bool_double_after_split_raises(self):
        with pytest.raises(ValueError):
            correct_action(['5', '6'], '6', dealer_hits_soft17=False, double_after_split='no')


class TestDasDependentPairCells:
    """
    All 5 pair cells whose chart value depends on double_after_split,
    checked under both DAS on and DAS off, and confirmed ruleset-independent
    (H17 vs S17) since the pairs table is shared.
    """

    @pytest.mark.parametrize('dealer_hits_soft17', [S17, H17])
    def test_six_six_vs_2(self, dealer_hits_soft17):
        assert _action(['6', '6'], '2', dealer_hits_soft17=dealer_hits_soft17, double_after_split=DAS_ON) == SPLIT
        # DAS off: 6,6 plays as hard 12 vs 2 -> Hit
        assert _action(['6', '6'], '2', dealer_hits_soft17=dealer_hits_soft17, double_after_split=DAS_OFF) == HIT

    @pytest.mark.parametrize('dealer_hits_soft17', [S17, H17])
    def test_four_four_vs_5(self, dealer_hits_soft17):
        assert _action(['4', '4'], '5', dealer_hits_soft17=dealer_hits_soft17, double_after_split=DAS_ON) == SPLIT
        # DAS off: 4,4 plays as hard 8 -> always Hit
        assert _action(['4', '4'], '5', dealer_hits_soft17=dealer_hits_soft17, double_after_split=DAS_OFF) == HIT

    @pytest.mark.parametrize('dealer_hits_soft17', [S17, H17])
    def test_four_four_vs_6(self, dealer_hits_soft17):
        assert _action(['4', '4'], '6', dealer_hits_soft17=dealer_hits_soft17, double_after_split=DAS_ON) == SPLIT
        assert _action(['4', '4'], '6', dealer_hits_soft17=dealer_hits_soft17, double_after_split=DAS_OFF) == HIT

    @pytest.mark.parametrize('dealer_hits_soft17', [S17, H17])
    def test_three_three_vs_2(self, dealer_hits_soft17):
        assert _action(['3', '3'], '2', dealer_hits_soft17=dealer_hits_soft17, double_after_split=DAS_ON) == SPLIT
        # DAS off: 3,3 plays as hard 6 -> below 8, default Hit
        assert _action(['3', '3'], '2', dealer_hits_soft17=dealer_hits_soft17, double_after_split=DAS_OFF) == HIT

    @pytest.mark.parametrize('dealer_hits_soft17', [S17, H17])
    def test_three_three_vs_3(self, dealer_hits_soft17):
        assert _action(['3', '3'], '3', dealer_hits_soft17=dealer_hits_soft17, double_after_split=DAS_ON) == SPLIT
        assert _action(['3', '3'], '3', dealer_hits_soft17=dealer_hits_soft17, double_after_split=DAS_OFF) == HIT

    @pytest.mark.parametrize('dealer_hits_soft17', [S17, H17])
    def test_two_two_vs_2(self, dealer_hits_soft17):
        assert _action(['2', '2'], '2', dealer_hits_soft17=dealer_hits_soft17, double_after_split=DAS_ON) == SPLIT
        # DAS off: 2,2 plays as hard 4 -> below 8, default Hit
        assert _action(['2', '2'], '2', dealer_hits_soft17=dealer_hits_soft17, double_after_split=DAS_OFF) == HIT

    @pytest.mark.parametrize('dealer_hits_soft17', [S17, H17])
    def test_two_two_vs_3(self, dealer_hits_soft17):
        assert _action(['2', '2'], '3', dealer_hits_soft17=dealer_hits_soft17, double_after_split=DAS_ON) == SPLIT
        assert _action(['2', '2'], '3', dealer_hits_soft17=dealer_hits_soft17, double_after_split=DAS_OFF) == HIT

    def test_pairs_not_das_dependent_are_ruleset_independent(self):
        # 8,8 vs A always splits regardless of DAS or H17/S17
        for h17 in (S17, H17):
            for das in (DAS_ON, DAS_OFF):
                assert _action(['8', '8'], 'A', dealer_hits_soft17=h17, double_after_split=das) == SPLIT


class TestH17VsS17HardTotalDivergence:
    def test_eleven_vs_ace_is_the_clearest_divergence(self):
        assert _action(['6', '5'], 'A', dealer_hits_soft17=S17) == HIT
        assert _action(['6', '5'], 'A', dealer_hits_soft17=H17) == DOUBLE

    def test_ace_eight_vs_six_diverges(self):
        assert _action(['A', '8'], '6', dealer_hits_soft17=S17) == STAND
        assert _action(['A', '8'], '6', dealer_hits_soft17=H17) == DOUBLE
