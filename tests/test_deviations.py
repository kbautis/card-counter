"""
Deviations - Test Suite
Covers hand_description classification and deviation threshold lookups
(both '+' and '-' directions) for the S17 Illustrious 18 index chart.
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from deviations import hand_description, deviation_lookup, deviation_triggered, DEVIATIONS
from basic_strategy import HIT, STAND, DOUBLE, SPLIT


class TestHandDescription:
    def test_pair_when_split_legal(self):
        assert hand_description(['10', '10'], can_split=True) == 'pair-10'
        assert hand_description(['K', 'Q'], can_split=True) == 'pair-10'

    def test_not_a_pair_description_when_split_illegal(self):
        # A hard/soft total, not a pair description, once split is off the table.
        assert hand_description(['8', '8'], can_split=False) == 'hard-16'

    def test_soft_total(self):
        assert hand_description(['A', '8'], can_split=False) == 'soft-19'
        assert hand_description(['A', '6'], can_split=False) == 'soft-17'

    def test_hard_total(self):
        assert hand_description(['10', '6'], can_split=False) == 'hard-16'
        assert hand_description(['9', '2'], can_split=False) == 'hard-11'


class TestDeviationLookup:
    def test_known_entry_found(self):
        entry = deviation_lookup('hard-16', '9')
        assert entry == {'direction': '+', 'threshold': 4, 'deviate_to': STAND}

    def test_unknown_entry_returns_none(self):
        assert deviation_lookup('hard-16', '2') is None
        assert deviation_lookup('hard-14', '9') is None

    def test_pair_ten_entries(self):
        assert deviation_lookup('pair-10', '4') == {'direction': '+', 'threshold': 6, 'deviate_to': SPLIT}
        assert deviation_lookup('pair-10', '5') == {'direction': '+', 'threshold': 5, 'deviate_to': SPLIT}
        assert deviation_lookup('pair-10', '6') == {'direction': '+', 'threshold': 4, 'deviate_to': SPLIT}

    def test_soft_entries(self):
        assert deviation_lookup('soft-19', '4') == {'direction': '+', 'threshold': 3, 'deviate_to': DOUBLE}
        assert deviation_lookup('soft-19', '5') == {'direction': '+', 'threshold': 1, 'deviate_to': DOUBLE}
        assert deviation_lookup('soft-19', '6') == {'direction': '+', 'threshold': 1, 'deviate_to': DOUBLE}
        assert deviation_lookup('soft-17', '2') == {'direction': '+', 'threshold': 1, 'deviate_to': DOUBLE}

    def test_all_21_source_entries_present(self):
        # 3 pairs + 4 soft + 14 hard, transcribed exactly from the CLAUDE.md source block.
        assert len(DEVIATIONS) == 21


class TestDeviationTriggered:
    def test_plus_direction_triggers_at_or_above_threshold(self):
        entry = {'direction': '+', 'threshold': 4, 'deviate_to': STAND}
        assert deviation_triggered(entry, 4) is True
        assert deviation_triggered(entry, 5) is True
        assert deviation_triggered(entry, 3.9) is False

    def test_minus_direction_triggers_at_or_below_threshold(self):
        entry = {'direction': '-', 'threshold': -1, 'deviate_to': HIT}
        assert deviation_triggered(entry, -1) is True
        assert deviation_triggered(entry, -2) is True
        assert deviation_triggered(entry, 0) is False

    def test_zero_threshold_plus_direction(self):
        # "16 vs 10: stand at 0+ (0 or above)"
        entry = deviation_lookup('hard-16', '10')
        assert deviation_triggered(entry, 0) is True
        assert deviation_triggered(entry, -0.5) is False

    def test_zero_threshold_minus_direction(self):
        # "12 vs 4: hit at 0 or below"
        entry = deviation_lookup('hard-12', '4')
        assert deviation_triggered(entry, 0) is True
        assert deviation_triggered(entry, 0.5) is False

    def test_none_entry_raises(self):
        with pytest.raises(ValueError):
            deviation_triggered(None, 5)
