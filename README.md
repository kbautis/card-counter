# Card Counter Trainer

A web app for practicing Hi-Lo card counting.

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

## How it works

1. Pick your number of decks (1–8) and card speed
2. Watch cards flip automatically
3. Keep a running Hi-Lo count in your head
4. When all cards are shown, enter your count
5. See if you were right — and by how much

## Hi-Lo System

| Cards | Value |
|-------|-------|
| 2, 3, 4, 5, 6 | +1 |
| 7, 8, 9 | 0 |
| 10, J, Q, K, A | −1 |

A full deck always sums to 0. The more positive the count, the more low cards
have been played — meaning high cards are more likely to appear next.

## Project structure

```
card-counter/
├── app.py              # Flask server
├── card_engine.py      # Core logic (deck, Hi-Lo, session, verify)
├── requirements.txt
├── static/
│   └── index.html      # Frontend UI
└── tests/
    └── test_card_engine.py   # Full test suite (TDD)
```
