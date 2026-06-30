"""Moteur d'intelligence artificielle.

Algorithme : Minimax (forme negamax) avec elagage Alpha-Beta,
approfondissement iteratif borne par le temps, table de transposition,
recherche de quiescence sur les captures, tri des coups (MVV-LVA).

Evaluation : materiel, controle du centre et activite (tables piece-case),
mobilite des pieces a longue portee, structure de pions (doubles, isoles,
passes), securite du roi (bouclier de pions), paire de fous.
"""

import random
import time

from engine import GameState

MATE = 100_000
PIECE_VALUES = {"P": 100, "N": 320, "B": 330, "R": 500, "Q": 900, "K": 0}

# Tables piece-case (point de vue blanc, ligne 0 = rangee 8).
# Les valeurs encouragent le controle du centre et l'activite des pieces.
PST_P = (
    (0, 0, 0, 0, 0, 0, 0, 0),
    (50, 50, 50, 50, 50, 50, 50, 50),
    (10, 10, 20, 30, 30, 20, 10, 10),
    (5, 5, 10, 25, 25, 10, 5, 5),
    (0, 0, 0, 20, 20, 0, 0, 0),
    (5, -5, -10, 0, 0, -10, -5, 5),
    (5, 10, 10, -20, -20, 10, 10, 5),
    (0, 0, 0, 0, 0, 0, 0, 0),
)
PST_N = (
    (-50, -40, -30, -30, -30, -30, -40, -50),
    (-40, -20, 0, 0, 0, 0, -20, -40),
    (-30, 0, 10, 15, 15, 10, 0, -30),
    (-30, 5, 15, 20, 20, 15, 5, -30),
    (-30, 0, 15, 20, 20, 15, 0, -30),
    (-30, 5, 10, 15, 15, 10, 5, -30),
    (-40, -20, 0, 5, 5, 0, -20, -40),
    (-50, -40, -30, -30, -30, -30, -40, -50),
)
PST_B = (
    (-20, -10, -10, -10, -10, -10, -10, -20),
    (-10, 0, 0, 0, 0, 0, 0, -10),
    (-10, 0, 5, 10, 10, 5, 0, -10),
    (-10, 5, 5, 10, 10, 5, 5, -10),
    (-10, 0, 10, 10, 10, 10, 0, -10),
    (-10, 10, 10, 10, 10, 10, 10, -10),
    (-10, 5, 0, 0, 0, 0, 5, -10),
    (-20, -10, -10, -10, -10, -10, -10, -20),
)
PST_R = (
    (0, 0, 0, 0, 0, 0, 0, 0),
    (5, 10, 10, 10, 10, 10, 10, 5),
    (-5, 0, 0, 0, 0, 0, 0, -5),
    (-5, 0, 0, 0, 0, 0, 0, -5),
    (-5, 0, 0, 0, 0, 0, 0, -5),
    (-5, 0, 0, 0, 0, 0, 0, -5),
    (-5, 0, 0, 0, 0, 0, 0, -5),
    (0, 0, 0, 5, 5, 0, 0, 0),
)
PST_Q = (
    (-20, -10, -10, -5, -5, -10, -10, -20),
    (-10, 0, 0, 0, 0, 0, 0, -10),
    (-10, 0, 5, 5, 5, 5, 0, -10),
    (-5, 0, 5, 5, 5, 5, 0, -5),
    (0, 0, 5, 5, 5, 5, 0, -5),
    (-10, 5, 5, 5, 5, 5, 0, -10),
    (-10, 0, 5, 0, 0, 0, 0, -10),
    (-20, -10, -10, -5, -5, -10, -10, -20),
)
PST_K_MID = (
    (-30, -40, -40, -50, -50, -40, -40, -30),
    (-30, -40, -40, -50, -50, -40, -40, -30),
    (-30, -40, -40, -50, -50, -40, -40, -30),
    (-30, -40, -40, -50, -50, -40, -40, -30),
    (-20, -30, -30, -40, -40, -30, -30, -20),
    (-10, -20, -20, -20, -20, -20, -20, -10),
    (20, 20, 0, 0, 0, 0, 20, 20),
    (20, 30, 10, 0, 0, 10, 30, 20),
)
PST_K_END = (
    (-50, -40, -30, -20, -20, -30, -40, -50),
    (-30, -20, -10, 0, 0, -10, -20, -30),
    (-30, -10, 20, 30, 30, 20, -10, -30),
    (-30, -10, 30, 40, 40, 30, -10, -30),
    (-30, -10, 30, 40, 40, 30, -10, -30),
    (-30, -10, 20, 30, 30, 20, -10, -30),
    (-30, -30, 0, 0, 0, 0, -30, -30),
    (-50, -30, -30, -30, -30, -30, -30, -50),
)
PST = {"P": PST_P, "N": PST_N, "B": PST_B, "R": PST_R, "Q": PST_Q}

# Niveaux de difficulte : profondeur maximale et budget temps (secondes)
LEVELS = {
    1: {"mode": "random"},
    2: {"depth": 2, "time": 0.8},
    3: {"depth": 4, "time": 1.0},
    4: {"depth": 5, "time": 4.0},
    5: {"depth": 8, "time": 5.0, "book": True},
}

# ---------------------------------------------------------------- ouvertures
# Livre d'ouvertures (niveau 5) : sequence de coups UCI -> reponses possibles
OPENING_BOOK = {
    (): ["e2e4", "d2d4", "g1f3", "c2c4"],
    # 1.e4
    ("e2e4",): ["e7e5", "c7c5", "e7e6", "c7c6"],
    ("e2e4", "e7e5"): ["g1f3"],
    ("e2e4", "e7e5", "g1f3"): ["b8c6"],
    ("e2e4", "e7e5", "g1f3", "b8c6"): ["f1b5", "f1c4", "d2d4"],
    # Espagnole
    ("e2e4", "e7e5", "g1f3", "b8c6", "f1b5"): ["a7a6", "g8f6"],
    ("e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6"): ["b5a4"],
    ("e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4"): ["g8f6"],
    ("e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6"): ["e1g1"],
    # Italienne
    ("e2e4", "e7e5", "g1f3", "b8c6", "f1c4"): ["f8c5", "g8f6"],
    ("e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5"): ["c2c3", "e1g1"],
    ("e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6"): ["d2d3", "e1g1"],
    # Sicilienne
    ("e2e4", "c7c5"): ["g1f3"],
    ("e2e4", "c7c5", "g1f3"): ["d7d6", "b8c6", "e7e6"],
    ("e2e4", "c7c5", "g1f3", "d7d6"): ["d2d4"],
    ("e2e4", "c7c5", "g1f3", "d7d6", "d2d4"): ["c5d4"],
    ("e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4"): ["f3d4"],
    ("e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4"): ["g8f6"],
    ("e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4", "g8f6"): ["b1c3"],
    # Francaise
    ("e2e4", "e7e6"): ["d2d4"],
    ("e2e4", "e7e6", "d2d4"): ["d7d5"],
    ("e2e4", "e7e6", "d2d4", "d7d5"): ["b1c3", "e4e5", "b1d2"],
    # Caro-Kann
    ("e2e4", "c7c6"): ["d2d4"],
    ("e2e4", "c7c6", "d2d4"): ["d7d5"],
    ("e2e4", "c7c6", "d2d4", "d7d5"): ["b1c3", "e4e5"],
    # 1.d4
    ("d2d4",): ["d7d5", "g8f6"],
    ("d2d4", "d7d5"): ["c2c4", "g1f3"],
    ("d2d4", "d7d5", "c2c4"): ["e7e6", "c7c6"],
    ("d2d4", "d7d5", "c2c4", "e7e6"): ["b1c3", "g1f3"],
    ("d2d4", "d7d5", "c2c4", "c7c6"): ["g1f3", "b1c3"],
    ("d2d4", "g8f6"): ["c2c4", "g1f3"],
    ("d2d4", "g8f6", "c2c4"): ["e7e6", "g7g6"],
    ("d2d4", "g8f6", "c2c4", "e7e6"): ["b1c3", "g1f3"],
    ("d2d4", "g8f6", "c2c4", "g7g6"): ["b1c3"],
    ("d2d4", "g8f6", "c2c4", "g7g6", "b1c3"): ["f8g7"],
    # 1.Nf3 / 1.c4
    ("g1f3",): ["d7d5", "g8f6"],
    ("c2c4",): ["e7e5", "g8f6", "c7c5"],
}


class SearchTimeout(Exception):
    pass


# ---------------------------------------------------------------- evaluation
def evaluate(gs):
    """Evaluation statique en centipions, positive si les blancs sont mieux."""
    b = gs.board
    score = 0
    white_pawn_files = [0] * 8
    black_pawn_files = [0] * 8
    white_bishops = black_bishops = 0
    phase_material = 0  # materiel hors pions/rois pour detecter la finale

    for r in range(8):
        for c in range(8):
            p = b[r][c]
            if not p:
                continue
            pt = p.upper()
            white = p.isupper()
            val = PIECE_VALUES[pt]
            if pt != "P":
                phase_material += val
            if pt == "K":
                continue
            pst = PST[pt]
            if white:
                score += val + pst[r][c]
                if pt == "P":
                    white_pawn_files[c] += 1
                elif pt == "B":
                    white_bishops += 1
            else:
                score -= val + pst[7 - r][c]
                if pt == "P":
                    black_pawn_files[c] += 1
                elif pt == "B":
                    black_bishops += 1
            # mobilite legere des pieces a longue portee
            if pt in ("B", "R", "Q"):
                mob = _ray_mobility(b, r, c, pt)
                score += mob if white else -mob

    endgame = phase_material < 1400

    # roi : table milieu de partie ou finale
    kr, kc = gs.wk
    score += (PST_K_END if endgame else PST_K_MID)[kr][kc]
    kr, kc = gs.bk
    score -= (PST_K_END if endgame else PST_K_MID)[7 - kr][kc]

    # paire de fous
    if white_bishops >= 2:
        score += 30
    if black_bishops >= 2:
        score -= 30

    # structure de pions
    score += _pawn_structure(white_pawn_files, black_pawn_files, b)

    # securite du roi (bouclier de pions), hors finale
    if not endgame:
        score += _king_shield(b, gs.wk, True) - _king_shield(b, gs.bk, False)

    return score


def _ray_mobility(b, r, c, pt):
    """Compte les cases accessibles sur les rayons (mobilite approximative)."""
    if pt == "B":
        dirs = ((-1, -1), (-1, 1), (1, -1), (1, 1))
        w = 3
    elif pt == "R":
        dirs = ((-1, 0), (1, 0), (0, -1), (0, 1))
        w = 2
    else:
        dirs = ((-1, -1), (-1, 1), (1, -1), (1, 1), (-1, 0), (1, 0), (0, -1), (0, 1))
        w = 1
    n = 0
    for dr, dc in dirs:
        r2, c2 = r + dr, c + dc
        while 0 <= r2 < 8 and 0 <= c2 < 8:
            n += 1
            if b[r2][c2]:
                break
            r2 += dr
            c2 += dc
    return n * w


def _pawn_structure(wf, bf, b):
    score = 0
    for c in range(8):
        # pions doubles
        if wf[c] > 1:
            score -= 15 * (wf[c] - 1)
        if bf[c] > 1:
            score += 15 * (bf[c] - 1)
        # pions isoles
        neighbors_w = (wf[c - 1] if c > 0 else 0) + (wf[c + 1] if c < 7 else 0)
        neighbors_b = (bf[c - 1] if c > 0 else 0) + (bf[c + 1] if c < 7 else 0)
        if wf[c] and not neighbors_w:
            score -= 12
        if bf[c] and not neighbors_b:
            score += 12
    # pions passes
    for r in range(8):
        for c in range(8):
            p = b[r][c]
            if p == "P":
                if not any(bf[c2] and _black_pawn_blocks(b, r, c2) for c2 in range(max(0, c - 1), min(8, c + 2))):
                    score += 15 + (6 - r) * 6
            elif p == "p":
                if not any(wf[c2] and _white_pawn_blocks(b, r, c2) for c2 in range(max(0, c - 1), min(8, c + 2))):
                    score -= 15 + (r - 1) * 6
    return score


def _black_pawn_blocks(b, r, c):
    return any(b[r2][c] == "p" for r2 in range(0, r))


def _white_pawn_blocks(b, r, c):
    return any(b[r2][c] == "P" for r2 in range(r + 1, 8))


def _king_shield(b, king, white):
    kr, kc = king
    d = -1 if white else 1
    pawn = "P" if white else "p"
    bonus = 0
    for dc in (-1, 0, 1):
        c = kc + dc
        if not 0 <= c < 8:
            continue
        r1 = kr + d
        if 0 <= r1 < 8 and b[r1][c] == pawn:
            bonus += 10
        elif 0 <= r1 + d < 8 and b[r1 + d][c] == pawn:
            bonus += 5
        else:
            bonus -= 8
    return bonus


# ----------------------------------------------------------------- recherche
class Searcher:
    def __init__(self, deadline):
        self.deadline = deadline
        self.nodes = 0
        self.tt = {}

    def _check_time(self):
        self.nodes += 1
        if self.nodes % 2048 == 0 and time.time() > self.deadline:
            raise SearchTimeout

    def order(self, moves, tt_move=None):
        def key(m):
            if tt_move and m == tt_move:
                return 10_000
            s = 0
            if m.captured:
                s = 1000 + 10 * PIECE_VALUES[m.captured.upper()] - PIECE_VALUES[m.piece.upper()]
            if m.promo:
                s += 900
            return s
        moves.sort(key=key, reverse=True)
        return moves

    def negamax(self, gs, depth, alpha, beta, ply):
        self._check_time()

        # nulles par regle (repetition / 50 coups / materiel)
        if ply > 0:
            if gs.rep.get(gs.key, 0) >= 3 or gs.halfmove >= 100 or gs.insufficient_material():
                return 0

        alpha_orig = alpha
        entry = self.tt.get(gs.key)
        tt_move = None
        if entry:
            e_depth, e_flag, e_score, tt_move = entry
            if e_depth >= depth and ply > 0:
                if e_flag == 0:
                    return e_score
                if e_flag == 1 and e_score >= beta:
                    return e_score
                if e_flag == 2 and e_score <= alpha:
                    return e_score

        if depth == 0:
            return self.qsearch(gs, alpha, beta, 0)

        moves = gs.legal_moves()
        if not moves:
            if gs.in_check(gs.white_to_move):
                return -MATE + ply  # mat : prefere les mats rapides
            return 0  # pat

        self.order(moves, tt_move)
        best = -MATE * 2
        best_move = None
        for m in moves:
            gs.make_move(m)
            score = -self.negamax(gs, depth - 1, -beta, -alpha, ply + 1)
            gs.unmake_move()
            if score > best:
                best = score
                best_move = m
            alpha = max(alpha, score)
            if alpha >= beta:
                break

        flag = 0 if alpha_orig < best < beta else (1 if best >= beta else 2)
        self.tt[gs.key] = (depth, flag, best, best_move)
        return best

    def qsearch(self, gs, alpha, beta, qply):
        self._check_time()
        color = 1 if gs.white_to_move else -1
        stand = color * evaluate(gs)
        if stand >= beta or qply >= 6:
            return max(stand, alpha) if qply >= 6 else beta
        alpha = max(alpha, stand)
        captures = gs.legal_moves(captures_only=True)
        self.order(captures)
        for m in captures:
            gs.make_move(m)
            score = -self.qsearch(gs, -beta, -alpha, qply + 1)
            gs.unmake_move()
            if score >= beta:
                return beta
            alpha = max(alpha, score)
        return alpha

    def search_root(self, gs, max_depth):
        """Approfondissement iteratif. Retourne (coup, score, profondeur atteinte)."""
        legal = gs.legal_moves()
        if not legal:
            return None, 0, 0
        if len(legal) == 1:
            return legal[0], 0, 0

        best_move, best_score, completed = legal[0], 0, 0
        for depth in range(1, max_depth + 1):
            try:
                self.order(legal, best_move)
                alpha = -MATE * 2
                local_best = None
                for m in legal:
                    gs.make_move(m)
                    score = -self.negamax(gs, depth - 1, -MATE * 2, -alpha, 1)
                    gs.unmake_move()
                    if score > alpha:
                        alpha = score
                        local_best = m
                best_move, best_score, completed = local_best, alpha, depth
                if abs(best_score) > MATE - 100:
                    break  # mat trouve, inutile de chercher plus loin
            except SearchTimeout:
                break
        return best_move, best_score, completed


# ------------------------------------------------------------------- niveaux
def _book_move(gs):
    """Cherche un coup dans le livre d'ouvertures (position initiale uniquement)."""
    from engine import START_FEN
    if gs.start_fen != START_FEN:
        return None
    seq = tuple(m.uci() for m in gs.move_log)
    candidates = OPENING_BOOK.get(seq)
    if not candidates:
        return None
    uci = random.choice(candidates)
    return gs.find_move(uci)


def _random_weighted(gs):
    """Niveau 1 : coup aleatoire pondere (prefere legerement les bons coups)."""
    moves = gs.legal_moves()
    if not moves:
        return None
    color = 1 if gs.white_to_move else -1
    weights = []
    for m in moves:
        gs.make_move(m)
        s = color * evaluate(gs)
        gs.unmake_move()
        weights.append(max(1.0, 50.0 + s / 25.0))
    return random.choices(moves, weights=weights, k=1)[0]


def choose_move(gs, level, on_info=None):
    """Choisit le coup de l'IA pour le niveau donne.

    Retourne (move, info) ou info contient eval (centipions, point de vue
    du camp au trait), profondeur atteinte, noeuds visites et duree.
    """
    cfg = LEVELS[max(1, min(5, level))]
    t0 = time.time()

    if cfg.get("mode") == "random":
        m = _random_weighted(gs)
        return m, {"eval": None, "depth": 0, "nodes": 0, "time": time.time() - t0}

    if cfg.get("book"):
        m = _book_move(gs)
        if m is not None:
            return m, {"eval": None, "depth": 0, "nodes": 0,
                       "time": time.time() - t0, "book": True}

    searcher = Searcher(deadline=t0 + cfg["time"])
    move, score, depth = searcher.search_root(gs, cfg["depth"])
    return move, {"eval": score, "depth": depth,
                  "nodes": searcher.nodes, "time": time.time() - t0}
