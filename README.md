# Card Counter Trainer

A web app for practicing Hi-Lo card counting and blackjack basic strategy.

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

Then open http://localhost:5000 in your browser.

## Test

```bash
python -m pytest tests/ -v
```

## Count Trainer

1. Pick your number of decks (1–8), card speed, and penetration
2. Watch cards flip automatically
3. Keep a running Hi-Lo count in your head
4. When all cards are shown (or you stop early), enter your count
5. See if you were right, by how much, and the true count

### Penetration

Penetration controls how much of the shoe gets dealt before you're asked
for your count — real shoes are cut short of the bottom, and counters have
to commit to an estimate before every card is seen. Pick a preset (Full /
Deep 75% / Medium 50% / Shallow 25%) or enter a custom exact number of
cards to deal.

### Hi-Lo System

| Cards | Value |
|-------|-------|
| 2, 3, 4, 5, 6 | +1 |
| 7, 8, 9 | 0 |
| 10, J, Q, K, A | −1 |

A full deck always sums to 0. The more positive the count, the more low
cards have been played — meaning high cards are more likely to appear next.

## Basic Strategy Trainer

Play real hands against a dealer. Configure the number of decks, the
number of hands to play, and shoe penetration, then make a decision on
every hand — Hit, Stand, Double, or Split — and get scored against the
standard basic strategy chart (multi-deck, dealer stands on soft 17,
double after split allowed, no surrender).

- **Hit / Stand / Double** are played out in full, including the dealer's
  turn, and count toward your win/loss/push record.
- **Split** is scored for strategy correctness only — the two resulting
  hands are not dealt out and played. This is a deliberate simplification
  (real re-splitting/doubling-after-split trees get deep fast); it still
  covers the ~90% of hands that aren't pairs end-to-end.
- The shoe reshuffles automatically once it's dealt past your chosen
  penetration, just like a real table.

## History & Progress

Every completed count-training round and basic-strategy session is logged
to your browser's local storage (nothing leaves your machine). The
**History** tab shows overall accuracy, your current count-training
streak, a trend chart of recent session accuracy, and a table of recent
sessions. Use "Clear History" to reset it.

## Project structure

```
card-counter/
├── app.py                        # Flask server (count + strategy routes)
├── card_engine.py                # Count-trainer logic (deck, Hi-Lo, session, verify)
├── basic_strategy.py             # Basic strategy chart lookup (hit/stand/double/split)
├── strategy_engine.py            # Hand-play session engine (deal, act, resolve, reshuffle)
├── requirements.txt
├── static/
│   └── index.html                # Frontend UI (count trainer, strategy trainer, history)
└── tests/
    ├── test_card_engine.py        # Count-trainer test suite (TDD)
    ├── test_basic_strategy.py     # Strategy chart test suite (TDD)
    └── test_strategy_engine.py    # Hand-play engine test suite (TDD)
```
