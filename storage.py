"""Gestionnaire de sauvegardes : enregistrement et chargement de parties (JSON)."""

import json
import os

from engine import GameState, START_FEN

SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saves")


def ensure_save_dir():
    os.makedirs(SAVE_DIR, exist_ok=True)
    return SAVE_DIR


def save_game(path, gs, meta=None):
    """Sauvegarde la partie : position de depart, coups joues et metadonnees."""
    data = {
        "version": 1,
        "start_fen": gs.start_fen,
        "moves": [m.uci() for m in gs.move_log],
        "meta": meta or {},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_game(path):
    """Recharge une partie sauvegardee. Retourne (GameState, meta)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    gs = GameState(data.get("start_fen", START_FEN))
    for uci in data["moves"]:
        m = gs.find_move(uci)
        if m is None:
            raise ValueError(f"Sauvegarde corrompue : coup illegal {uci!r}")
        gs.make_move(m)
    return gs, data.get("meta", {})
