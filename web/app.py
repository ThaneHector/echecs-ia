"""Serveur web Flask — Échecs IA avec multijoueur en ligne et Elo."""
import sys
import os
import json
import uuid
import math
import threading
import time as _time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, jsonify, request, abort
from engine import GameState, START_FEN
from ai import Searcher

app = Flask(__name__, static_folder="static", static_url_path="")

# ── État global ───────────────────────────────────────────────────────────────
_games: dict = {}   # gid -> {"gs", "mode", "ai_color", "level", "p1", "p2", "p1_token", "p2_token"}
_rooms: dict = {}   # rid -> {"gid", "p1", "p1_token", "p2", "p2_token", "joined"}
_elo: dict = {}     # name -> rating (int)
_lock = threading.Lock()

ELO_FILE = Path.home() / ".echecs_ia" / "elo.json"
LEVEL_DEPTH = {"Débutant": 1, "Amateur": 2, "Confirmé": 3, "Expert": 4}
LEVEL_TIME  = {"Débutant": 0.1, "Amateur": 0.3, "Confirmé": 0.8, "Expert": 2.0}

# ── Elo ───────────────────────────────────────────────────────────────────────

def _load_elo():
    global _elo
    ELO_FILE.parent.mkdir(parents=True, exist_ok=True)
    if ELO_FILE.exists():
        with open(ELO_FILE) as f:
            _elo = json.load(f)

def _save_elo():
    ELO_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ELO_FILE, "w") as f:
        json.dump(_elo, f, indent=2)

def get_elo(name: str) -> int:
    return _elo.get(name, 1200)

def update_elo(winner: str, loser: str, draw: bool = False):
    ra, rb = get_elo(winner), get_elo(loser)
    ea = 1 / (1 + 10 ** ((rb - ra) / 400))
    eb = 1 - ea
    k = 32
    sa, sb = (0.5, 0.5) if draw else (1.0, 0.0)
    _elo[winner] = round(ra + k * (sa - ea))
    _elo[loser]  = round(rb + k * (sb - eb))
    _save_elo()

_load_elo()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _board_json(gs: GameState):
    """Sérialise le plateau pour le frontend."""
    board = []
    for r in range(8):
        row = []
        for c in range(8):
            row.append(gs.board[r][c])
        board.append(row)

    legal = {}
    for m in gs.legal_moves():
        key = f"{m.sr},{m.sc}"
        legal.setdefault(key, []).append(f"{m.er},{m.ec}" + (f"={m.promo}" if m.promo else ""))

    result = gs.result()
    if result is None:
        status = "playing"
        reason = ""
    else:
        score, reason = result
        if "mat" in reason.lower():
            status = "checkmate"
        elif reason == "Pat":
            status = "stalemate"
        else:
            status = "draw"

    in_check = gs.in_check(gs.white_to_move)

    return {
        "board": board,
        "white_to_move": gs.white_to_move,
        "legal": legal,
        "status": status,
        "reason": reason,
        "in_check": in_check,
        "move_log": [m.uci() for m in gs.move_log],
        "halfmove": gs.halfmove,
        "fullmove": gs.fullmove,
    }

def _ai_move(gs: GameState, level: str):
    """Fait jouer l'IA et retourne le coup UCI."""
    depth = LEVEL_DEPTH.get(level, 2)
    tl    = LEVEL_TIME.get(level, 0.5)
    searcher = Searcher(deadline=_time.time() + tl)
    move, _, _ = searcher.search_root(gs, depth)
    if move:
        gs.make_move(move)
        return move.uci()
    return None

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/elo", methods=["GET"])
def api_elo():
    rankings = sorted(_elo.items(), key=lambda x: -x[1])
    return jsonify(rankings)


@app.route("/api/new", methods=["POST"])
def api_new():
    data = request.get_json(force=True)
    mode    = data.get("mode", "vs_ia")   # "vs_ia" | "local_2p"
    level   = data.get("level", "Confirmé")
    p1_name = data.get("p1", "Joueur")
    p2_name = data.get("p2", "Joueur 2")
    # human plays white by default vs IA (ai_color = "b")
    ai_color = data.get("ai_color", "b")  # "w" ou "b"

    gs = GameState()
    gid = str(uuid.uuid4())[:8]
    _games[gid] = {
        "gs": gs,
        "mode": mode,
        "ai_color": ai_color,
        "level": level,
        "p1": p1_name,
        "p2": p2_name if mode == "local_2p" else f"IA ({level})",
        "p1_token": None,
        "p2_token": None,
    }

    state = _board_json(gs)
    state["gid"] = gid
    state["mode"] = mode
    state["p1"] = _games[gid]["p1"]
    state["p2"] = _games[gid]["p2"]
    state["ai_color"] = ai_color

    # Si IA joue blanc, elle joue d'abord
    if mode == "vs_ia" and ai_color == "w":
        ai_uci = _ai_move(gs, level)
        state = _board_json(gs)
        state["gid"] = gid
        state["mode"] = mode
        state["p1"] = _games[gid]["p1"]
        state["p2"] = _games[gid]["p2"]
        state["ai_color"] = ai_color
        state["ai_uci"] = ai_uci

    return jsonify(state)


@app.route("/api/game/<gid>/state", methods=["GET"])
def api_state(gid):
    token = request.args.get("token")
    entry = _games.get(gid)
    if not entry:
        abort(404)
    state = _board_json(entry["gs"])
    state["gid"] = gid
    state["mode"] = entry["mode"]
    state["p1"] = entry["p1"]
    state["p2"] = entry["p2"]
    state["ai_color"] = entry.get("ai_color", "b")
    if token:
        if token == entry.get("p1_token"):
            state["my_color"] = "w"
        elif token == entry.get("p2_token"):
            state["my_color"] = "b"
    return jsonify(state)


@app.route("/api/game/<gid>/move", methods=["POST"])
def api_move(gid):
    """Jouer un coup (partie locale vs IA ou 2 joueurs local)."""
    entry = _games.get(gid)
    if not entry:
        abort(404)
    data = request.get_json(force=True)
    uci  = data.get("uci", "")

    gs = entry["gs"]
    move = gs.find_move(uci)
    if move is None:
        return jsonify({"error": "Coup illégal"}), 400

    gs.make_move(move)
    state = _board_json(gs)
    state["gid"] = gid
    state["mode"] = entry["mode"]
    state["p1"] = entry["p1"]
    state["p2"] = entry["p2"]
    state["ai_color"] = entry.get("ai_color", "b")
    state["last_uci"] = uci

    # IA répond si mode vs_ia et ce n'est pas terminé
    if entry["mode"] == "vs_ia" and state["status"] == "playing":
        ai_uci = _ai_move(gs, entry["level"])
        state = _board_json(gs)
        state["gid"] = gid
        state["mode"] = entry["mode"]
        state["p1"] = entry["p1"]
        state["p2"] = entry["p2"]
        state["ai_color"] = entry.get("ai_color", "b")
        state["last_uci"] = uci
        state["ai_uci"] = ai_uci

        # Mise à jour Elo si la partie est finie
        if state["status"] in ("checkmate", "stalemate", "draw"):
            _handle_game_end(entry, state["status"])

    return jsonify(state)


@app.route("/api/game/<gid>/move_as", methods=["POST"])
def api_move_as(gid):
    """Jouer un coup en mode en ligne (avec token)."""
    entry = _games.get(gid)
    if not entry:
        abort(404)
    data  = request.get_json(force=True)
    token = data.get("token", "")
    uci   = data.get("uci", "")

    gs = entry["gs"]
    # Vérifier que c'est bien le tour du bon joueur
    is_p1 = token == entry.get("p1_token")
    is_p2 = token == entry.get("p2_token")
    if not is_p1 and not is_p2:
        return jsonify({"error": "Token invalide"}), 403

    # p1 joue blanc, p2 joue noir
    if (is_p1 and not gs.white_to_move) or (is_p2 and gs.white_to_move):
        return jsonify({"error": "Ce n'est pas votre tour"}), 400

    move = gs.find_move(uci)
    if move is None:
        return jsonify({"error": "Coup illégal"}), 400

    gs.make_move(move)
    state = _board_json(gs)
    state["gid"] = gid
    state["mode"] = entry["mode"]
    state["p1"] = entry["p1"]
    state["p2"] = entry["p2"]
    state["last_uci"] = uci
    state["my_color"] = "w" if is_p1 else "b"

    if state["status"] in ("checkmate", "stalemate", "draw"):
        _handle_game_end(entry, state["status"])

    return jsonify(state)


def _handle_game_end(entry, status):
    p1, p2 = entry["p1"], entry["p2"]
    mode = entry["mode"]
    if mode == "vs_ia":
        return  # pas d'Elo contre l'IA (ou on peut ajouter IA fictif)
    # multijoueur : mettre à jour Elo
    gs = entry["gs"]
    if status == "checkmate":
        # dernier joueur à avoir joué a fait mat = vainqueur
        white_won = not gs.white_to_move  # après le coup, c'est à l'autre de jouer
        if white_won:
            update_elo(p1, p2)
        else:
            update_elo(p2, p1)
    elif status in ("stalemate", "draw"):
        update_elo(p1, p2, draw=True)


@app.route("/api/game/<gid>/resign", methods=["POST"])
def api_resign(gid):
    entry = _games.get(gid)
    if not entry:
        abort(404)
    data  = request.get_json(force=True)
    token = data.get("token")
    p1, p2 = entry["p1"], entry["p2"]
    if token == entry.get("p2_token"):
        update_elo(p1, p2)
    elif token == entry.get("p1_token"):
        update_elo(p2, p1)
    return jsonify({"ok": True, "elo_w": get_elo(p1), "elo_b": get_elo(p2)})


# ── Salons multijoueur ────────────────────────────────────────────────────────

@app.route("/api/room", methods=["POST"])
def api_create_room():
    data = request.get_json(force=True)
    p1_name = data.get("name", "Joueur")
    rid = str(uuid.uuid4())[:6].upper()
    token = str(uuid.uuid4())
    _rooms[rid] = {
        "gid": None,
        "p1": p1_name,
        "p1_token": token,
        "p2": None,
        "p2_token": None,
        "joined": False,
    }
    return jsonify({"rid": rid, "token": token, "p1": p1_name})


@app.route("/api/room/<rid>", methods=["GET"])
def api_room_status(rid):
    room = _rooms.get(rid)
    if not room:
        abort(404)
    return jsonify({
        "rid": rid,
        "p1": room["p1"],
        "p2": room["p2"],
        "joined": room["joined"],
        "gid": room["gid"],
    })


@app.route("/api/room/<rid>/join", methods=["POST"])
def api_join_room(rid):
    room = _rooms.get(rid)
    if not room:
        abort(404)
    if room["joined"]:
        return jsonify({"error": "Salle déjà complète"}), 400
    data = request.get_json(force=True)
    p2_name = data.get("name", "Joueur 2")
    p2_token = str(uuid.uuid4())

    # Créer la partie
    gs = GameState()
    gid = str(uuid.uuid4())[:8]
    _games[gid] = {
        "gs": gs,
        "mode": "online_2p",
        "ai_color": None,
        "level": None,
        "p1": room["p1"],
        "p2": p2_name,
        "p1_token": room["p1_token"],
        "p2_token": p2_token,
    }
    room["p2"] = p2_name
    room["p2_token"] = p2_token
    room["gid"] = gid
    room["joined"] = True

    return jsonify({"gid": gid, "token": p2_token, "p1": room["p1"], "p2": p2_name})


# ── Démarrage ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081, debug=True)
