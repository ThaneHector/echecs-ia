"""Module statistiques : indicateurs de partie et analyse post-partie.

Statistiques : pieces capturees, temps moyen par coup, precision estimee.
Analyse : detection des impressions, erreurs et gaffes en comparant chaque
coup joue au meilleur coup trouve par le moteur.
"""

import time

from engine import GameState
from ai import Searcher, MATE

PIECE_ORDER = "QRBNP"

SEUILS = (
    (300, "Gaffe"),
    (120, "Erreur"),
    (50, "Imprecision"),
)


def captured_pieces(gs):
    """Pieces capturees depuis le debut. Retourne (prises_par_blancs, prises_par_noirs)."""
    by_white, by_black = [], []
    for m in gs.move_log:
        if m.captured:
            if m.captured.isupper():
                by_black.append(m.captured)
            else:
                by_white.append(m.captured.upper())
    key = PIECE_ORDER.index
    return sorted(by_white, key=key), sorted(by_black, key=key)


def material_balance(captures_white, captures_black):
    """Difference materielle (>0 : avantage blanc) sur la base des captures."""
    values = {"P": 1, "N": 3, "B": 3, "R": 5, "Q": 9}
    return (sum(values[p] for p in captures_white)
            - sum(values[p] for p in captures_black))


class GameStats:
    """Suivi en cours de partie : temps de reflexion par coup."""

    def __init__(self):
        self.move_times = {"w": [], "b": []}
        self._turn_start = time.time()

    def start_turn(self):
        self._turn_start = time.time()

    def record_move(self, white):
        self.move_times["w" if white else "b"].append(time.time() - self._turn_start)
        self._turn_start = time.time()

    def average_time(self, white):
        times = self.move_times["w" if white else "b"]
        return sum(times) / len(times) if times else 0.0


def _score_move(gs, move, depth, time_budget):
    """Evalue un coup donne et le meilleur coup de la position (negamax)."""
    searcher = Searcher(deadline=time.time() + time_budget)
    best_move, best_score, _ = searcher.search_root(gs, depth)
    gs.make_move(move)
    try:
        played_score = -searcher.negamax(gs, depth - 1, -MATE * 2, MATE * 2, 1)
    except Exception:
        played_score = best_score
    finally:
        gs.unmake_move()
    return best_score, played_score, best_move


def analyse_game(moves_uci, start_fen=None, depth=3, time_per_move=0.6,
                 progress=None):
    """Analyse post-partie.

    Retourne une liste de dicts {ply, uci, loss, label, best_uci} et les
    precisions blanche et noire (0-100).
    """
    gs = GameState(start_fen) if start_fen else GameState()
    report = []
    losses = {"w": [], "b": []}

    for i, uci in enumerate(moves_uci):
        move = gs.find_move(uci)
        if move is None:
            break
        mover = "w" if gs.white_to_move else "b"
        best_score, played_score, best_move = _score_move(gs, move, depth, time_per_move)
        loss = max(0, best_score - played_score)
        label = ""
        for seuil, nom in SEUILS:
            if loss >= seuil:
                label = nom
                break
        report.append({
            "ply": i + 1,
            "uci": uci,
            "loss": loss,
            "label": label,
            "best_uci": best_move.uci() if best_move else "",
        })
        losses[mover].append(min(loss, 1000))
        gs.make_move(move)
        if progress:
            progress(i + 1, len(moves_uci))

    def precision(side):
        vals = losses[side]
        if not vals:
            return 100.0
        avg = sum(vals) / len(vals)
        return round(max(0.0, 100.0 - avg / 5.0), 1)

    return report, precision("w"), precision("b")
