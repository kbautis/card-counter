"""
app.py — Flask web server for the card counting trainer.

Routes:
  GET  /            → serve the UI
  POST /api/session → create a new game session
  POST /api/verify  → verify the user's count (supports early-stop via cards_shown)

Session data is held in the in-memory _SESSIONS store (keyed by UUID) rather
than in Flask's cookie session so that the shoe's hi_lo_values list never hits
the 4 KB cookie limit for large multi-deck shoes.  Sessions expire after
SESSION_TTL_SECONDS to prevent unbounded memory growth.
"""
import os
import uuid
import time
from flask import Flask, request, jsonify
from card_engine import create_session, verify_answer, calculate_true_count, MIN_CARDS

app = Flask(__name__)
app.secret_key = os.urandom(24)

_HTML_PATH = os.path.join(os.path.dirname(__file__), 'static', 'index.html')

# In-memory session store: session_id → game metadata
_SESSIONS: dict[str, dict] = {}
SESSION_TTL_SECONDS = 3600  # 1 hour


def _purge_expired_sessions() -> None:
    """Remove sessions older than SESSION_TTL_SECONDS."""
    cutoff = time.time() - SESSION_TTL_SECONDS
    expired = [sid for sid, data in _SESSIONS.items() if data['created_at'] < cutoff]
    for sid in expired:
        del _SESSIONS[sid]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get('/')
def index():
    try:
        return open(_HTML_PATH).read(), 200, {'Content-Type': 'text/html'}
    except FileNotFoundError:
        return "UI not found — ensure static/index.html exists.", 500


@app.post('/api/session')
def new_session():
    data = request.get_json(silent=True) or {}

    num_decks   = data.get('num_decks', 1)
    interval_ms = data.get('interval_ms', 1500)
    num_cards   = data.get('num_cards')      # None → full shoe

    if not isinstance(num_decks, int) or not (1 <= num_decks <= 8):
        return jsonify(error="num_decks must be an integer between 1 and 8"), 400
    if not isinstance(interval_ms, int) or interval_ms <= 0:
        return jsonify(error="interval_ms must be a positive integer"), 400
    if num_cards is not None:
        max_cards = num_decks * 52
        if not isinstance(num_cards, int) or not (MIN_CARDS <= num_cards <= max_cards):
            return jsonify(
                error=f"num_cards must be an integer between {MIN_CARDS} and {max_cards}"
            ), 400

    game = create_session(
        num_decks=num_decks,
        interval_ms=interval_ms,
        num_cards=num_cards,
    )

    # Persist hi_lo_values server-side so early-stop verification works without
    # sending the answer to the client.
    session_id = str(uuid.uuid4())
    _SESSIONS[session_id] = {
        'hi_lo_values':    game['hi_lo_values'],
        'num_decks':       game['num_decks'],
        'total_shoe_size': game['total_shoe_size'],
        'cards_dealt':     game['cards_dealt'],
        'created_at':      time.time(),
    }

    return jsonify({
        'session_id':      session_id,
        'cards':           game['cards'],
        'num_decks':       game['num_decks'],
        'interval_ms':     game['interval_ms'],
        'total_cards':     len(game['cards']),
        'total_shoe_size': game['total_shoe_size'],
    })


@app.post('/api/verify')
def verify():
    _purge_expired_sessions()

    data       = request.get_json(silent=True) or {}
    session_id = data.get('session_id')
    user_count = data.get('user_count')
    cards_shown = data.get('cards_shown')   # int or None; None → all dealt cards

    if not session_id or session_id not in _SESSIONS:
        return jsonify(error="Invalid or expired session — start a new game first"), 400
    if user_count is None or not isinstance(user_count, int):
        return jsonify(error="user_count must be an integer"), 400

    game_data   = _SESSIONS.pop(session_id)
    hi_lo_vals  = game_data['hi_lo_values']
    max_shown   = len(hi_lo_vals)

    if cards_shown is None:
        cards_shown = max_shown
    elif not isinstance(cards_shown, int) or not (1 <= cards_shown <= max_shown):
        return jsonify(error=f"cards_shown must be between 1 and {max_shown}"), 400

    correct_count = sum(hi_lo_vals[:cards_shown])
    result        = verify_answer(correct_count, user_count)

    # True count (None if full shoe was dealt — no decks remain)
    true_count = calculate_true_count(
        running_count=correct_count,
        total_shoe_cards=game_data['total_shoe_size'],
        cards_dealt=cards_shown,
    )
    result['true_count']    = round(true_count, 2) if true_count is not None else None
    result['cards_shown']   = cards_shown
    result['total_shoe_size'] = game_data['total_shoe_size']

    return jsonify(result)


if __name__ == '__main__':
    app.run(debug=True, port=5000)
