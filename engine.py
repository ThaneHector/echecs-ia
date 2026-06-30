"""Moteur de regles d'echecs conforme aux regles FIDE.

Representation du plateau : matrice 8x8 (liste de listes).
- ligne 0 = rangee 8 (camp noir), ligne 7 = rangee 1 (camp blanc)
- pieces blanches en majuscules ("PNBRQK"), noires en minuscules ("pnbrqk")
- case vide = chaine vide ""

Regles couvertes : roque, prise en passant, promotion, pat, echec et mat,
triple repetition, regle des 50 coups, materiel insuffisant.
"""

import random

FILES = "abcdefgh"
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
PIECE_LETTERS = "PNBRQKpnbrqk"

# --- Hachage Zobrist (cles de position pour repetition et table de transposition)
_rng = random.Random(20260612)
Z_PIECE = {(p, sq): _rng.getrandbits(64) for p in PIECE_LETTERS for sq in range(64)}
Z_SIDE = _rng.getrandbits(64)
Z_CASTLE = {c: _rng.getrandbits(64) for c in "KQkq"}
Z_EP = [_rng.getrandbits(64) for _ in range(8)]

KNIGHT_STEPS = ((-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1))
KING_STEPS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
ROOK_DIRS = ((-1, 0), (1, 0), (0, -1), (0, 1))
BISHOP_DIRS = ((-1, -1), (-1, 1), (1, -1), (1, 1))


def sq_name(r, c):
    """Coordonnees matrice -> nom de case ('e4')."""
    return FILES[c] + str(8 - r)


def parse_sq(name):
    """Nom de case ('e4') -> coordonnees matrice (ligne, colonne)."""
    return 8 - int(name[1]), FILES.index(name[0])


class Move:
    """Un coup, avec l'etat necessaire pour pouvoir l'annuler (unmake)."""

    __slots__ = ("sr", "sc", "er", "ec", "piece", "captured", "promo",
                 "is_ep", "is_castle",
                 "prev_castling", "prev_ep", "prev_halfmove", "prev_key")

    def __init__(self, sr, sc, er, ec, piece, captured="", promo=None,
                 is_ep=False, is_castle=False):
        self.sr, self.sc, self.er, self.ec = sr, sc, er, ec
        self.piece = piece
        self.captured = captured
        self.promo = promo
        self.is_ep = is_ep
        self.is_castle = is_castle
        self.prev_castling = None
        self.prev_ep = None
        self.prev_halfmove = 0
        self.prev_key = 0

    def uci(self):
        s = sq_name(self.sr, self.sc) + sq_name(self.er, self.ec)
        if self.promo:
            s += self.promo.lower()
        return s

    def __eq__(self, other):
        return (isinstance(other, Move)
                and (self.sr, self.sc, self.er, self.ec, self.promo)
                == (other.sr, other.sc, other.er, other.ec, other.promo))

    def __hash__(self):
        return hash((self.sr, self.sc, self.er, self.ec, self.promo))

    def __repr__(self):
        return f"Move({self.uci()})"


class GameState:
    """Etat complet d'une partie : plateau, trait, droits, horloges de regle."""

    def __init__(self, fen=START_FEN):
        self.board = [[""] * 8 for _ in range(8)]
        self.white_to_move = True
        self.castling = set()       # sous-ensemble de {"K","Q","k","q"}
        self.ep = None              # case de prise en passant (r, c) ou None
        self.halfmove = 0           # compteur de la regle des 50 coups
        self.fullmove = 1
        self.move_log = []
        self.load_fen(fen)

    # ------------------------------------------------------------------ FEN
    def load_fen(self, fen):
        parts = fen.split()
        rows = parts[0].split("/")
        for r in range(8):
            c = 0
            for ch in rows[r]:
                if ch.isdigit():
                    for _ in range(int(ch)):
                        self.board[r][c] = ""
                        c += 1
                else:
                    self.board[r][c] = ch
                    c += 1
        self.white_to_move = parts[1] == "w"
        self.castling = set(parts[2]) if parts[2] != "-" else set()
        self.ep = parse_sq(parts[3]) if parts[3] != "-" else None
        self.halfmove = int(parts[4]) if len(parts) > 4 else 0
        self.fullmove = int(parts[5]) if len(parts) > 5 else 1
        self.move_log = []
        self.start_fen = fen
        self._locate_kings()
        self.key = self._compute_key()
        self.rep = {self.key: 1}

    def to_fen(self):
        rows = []
        for r in range(8):
            row, empty = "", 0
            for c in range(8):
                p = self.board[r][c]
                if p:
                    if empty:
                        row += str(empty)
                        empty = 0
                    row += p
                else:
                    empty += 1
            if empty:
                row += str(empty)
            rows.append(row)
        castle = "".join(c for c in "KQkq" if c in self.castling) or "-"
        ep = sq_name(*self.ep) if self.ep else "-"
        return " ".join(["/".join(rows), "w" if self.white_to_move else "b",
                         castle, ep, str(self.halfmove), str(self.fullmove)])

    def _locate_kings(self):
        for r in range(8):
            for c in range(8):
                if self.board[r][c] == "K":
                    self.wk = (r, c)
                elif self.board[r][c] == "k":
                    self.bk = (r, c)

    def _compute_key(self):
        k = 0
        for r in range(8):
            for c in range(8):
                p = self.board[r][c]
                if p:
                    k ^= Z_PIECE[(p, r * 8 + c)]
        if not self.white_to_move:
            k ^= Z_SIDE
        k ^= self._castle_ep_key()
        return k

    def _castle_ep_key(self):
        k = 0
        for cr in self.castling:
            k ^= Z_CASTLE[cr]
        if self.ep:
            k ^= Z_EP[self.ep[1]]
        return k

    # ------------------------------------------------------- jouer / annuler
    def make_move(self, m):
        b = self.board
        m.prev_castling = self.castling.copy()
        m.prev_ep = self.ep
        m.prev_halfmove = self.halfmove
        m.prev_key = self.key

        self.key ^= self._castle_ep_key()
        piece = m.piece
        b[m.sr][m.sc] = ""
        self.key ^= Z_PIECE[(piece, m.sr * 8 + m.sc)]

        if m.is_ep:
            b[m.sr][m.ec] = ""
            self.key ^= Z_PIECE[(m.captured, m.sr * 8 + m.ec)]
        elif m.captured:
            self.key ^= Z_PIECE[(m.captured, m.er * 8 + m.ec)]

        placed = m.promo if m.promo else piece
        b[m.er][m.ec] = placed
        self.key ^= Z_PIECE[(placed, m.er * 8 + m.ec)]

        if m.is_castle:
            row = m.sr
            if m.ec == 6:    # petit roque
                rook = b[row][7]
                b[row][7] = ""
                b[row][5] = rook
                self.key ^= Z_PIECE[(rook, row * 8 + 7)] ^ Z_PIECE[(rook, row * 8 + 5)]
            else:            # grand roque
                rook = b[row][0]
                b[row][0] = ""
                b[row][3] = rook
                self.key ^= Z_PIECE[(rook, row * 8 + 0)] ^ Z_PIECE[(rook, row * 8 + 3)]

        # droits de roque
        if piece == "K":
            self.castling -= {"K", "Q"}
            self.wk = (m.er, m.ec)
        elif piece == "k":
            self.castling -= {"k", "q"}
            self.bk = (m.er, m.ec)
        for (r, c, right) in ((7, 0, "Q"), (7, 7, "K"), (0, 0, "q"), (0, 7, "k")):
            if (m.sr, m.sc) == (r, c) or (m.er, m.ec) == (r, c):
                self.castling.discard(right)

        # case de prise en passant (uniquement si une capture est possible)
        self.ep = None
        if piece in ("P", "p") and abs(m.er - m.sr) == 2:
            enemy_pawn = "p" if piece == "P" else "P"
            for dc in (-1, 1):
                c2 = m.ec + dc
                if 0 <= c2 < 8 and b[m.er][c2] == enemy_pawn:
                    self.ep = ((m.sr + m.er) // 2, m.ec)
                    break

        # regle des 50 coups
        if piece in ("P", "p") or m.captured:
            self.halfmove = 0
        else:
            self.halfmove += 1

        if not self.white_to_move:
            self.fullmove += 1
        self.white_to_move = not self.white_to_move

        self.key ^= Z_SIDE
        self.key ^= self._castle_ep_key()
        self.rep[self.key] = self.rep.get(self.key, 0) + 1
        self.move_log.append(m)

    def unmake_move(self):
        m = self.move_log.pop()
        n = self.rep.get(self.key, 0) - 1
        if n <= 0:
            self.rep.pop(self.key, None)
        else:
            self.rep[self.key] = n

        b = self.board
        b[m.sr][m.sc] = m.piece
        b[m.er][m.ec] = ""
        if m.is_ep:
            b[m.sr][m.ec] = m.captured
        elif m.captured:
            b[m.er][m.ec] = m.captured
        if m.is_castle:
            row = m.sr
            if m.ec == 6:
                b[row][5], b[row][7] = "", b[row][5]
            else:
                b[row][3], b[row][0] = "", b[row][3]
        if m.piece == "K":
            self.wk = (m.sr, m.sc)
        elif m.piece == "k":
            self.bk = (m.sr, m.sc)

        self.castling = m.prev_castling
        self.ep = m.prev_ep
        self.halfmove = m.prev_halfmove
        self.key = m.prev_key
        self.white_to_move = not self.white_to_move
        if not self.white_to_move:
            self.fullmove -= 1

    # ----------------------------------------------------------- attaques
    def square_attacked(self, r, c, by_white):
        b = self.board
        # pions
        if by_white:
            for dc in (-1, 1):
                r2, c2 = r + 1, c + dc
                if 0 <= r2 < 8 and 0 <= c2 < 8 and b[r2][c2] == "P":
                    return True
        else:
            for dc in (-1, 1):
                r2, c2 = r - 1, c + dc
                if 0 <= r2 < 8 and 0 <= c2 < 8 and b[r2][c2] == "p":
                    return True
        knight = "N" if by_white else "n"
        for dr, dc in KNIGHT_STEPS:
            r2, c2 = r + dr, c + dc
            if 0 <= r2 < 8 and 0 <= c2 < 8 and b[r2][c2] == knight:
                return True
        king = "K" if by_white else "k"
        for dr, dc in KING_STEPS:
            r2, c2 = r + dr, c + dc
            if 0 <= r2 < 8 and 0 <= c2 < 8 and b[r2][c2] == king:
                return True
        rq = ("R", "Q") if by_white else ("r", "q")
        for dr, dc in ROOK_DIRS:
            r2, c2 = r + dr, c + dc
            while 0 <= r2 < 8 and 0 <= c2 < 8:
                p = b[r2][c2]
                if p:
                    if p in rq:
                        return True
                    break
                r2 += dr
                c2 += dc
        bq = ("B", "Q") if by_white else ("b", "q")
        for dr, dc in BISHOP_DIRS:
            r2, c2 = r + dr, c + dc
            while 0 <= r2 < 8 and 0 <= c2 < 8:
                p = b[r2][c2]
                if p:
                    if p in bq:
                        return True
                    break
                r2 += dr
                c2 += dc
        return False

    def in_check(self, white):
        kr, kc = self.wk if white else self.bk
        return self.square_attacked(kr, kc, not white)

    # ---------------------------------------------------- generation de coups
    def generate_pseudo(self, captures_only=False):
        """Tous les coups pseudo-legaux du camp au trait."""
        moves = []
        b = self.board
        white = self.white_to_move
        own_upper = white
        for r in range(8):
            for c in range(8):
                p = b[r][c]
                if not p or p.isupper() != own_upper:
                    continue
                pt = p.upper()
                if pt == "P":
                    self._pawn_moves(r, c, p, moves, captures_only)
                elif pt == "N":
                    for dr, dc in KNIGHT_STEPS:
                        self._step_move(r, c, p, r + dr, c + dc, moves, captures_only)
                elif pt == "K":
                    for dr, dc in KING_STEPS:
                        self._step_move(r, c, p, r + dr, c + dc, moves, captures_only)
                    if not captures_only:
                        self._castle_moves(r, c, p, moves)
                else:
                    dirs = (ROOK_DIRS if pt == "R" else
                            BISHOP_DIRS if pt == "B" else
                            ROOK_DIRS + BISHOP_DIRS)
                    for dr, dc in dirs:
                        r2, c2 = r + dr, c + dc
                        while 0 <= r2 < 8 and 0 <= c2 < 8:
                            t = b[r2][c2]
                            if t:
                                if t.isupper() != own_upper:
                                    moves.append(Move(r, c, r2, c2, p, t))
                                break
                            if not captures_only:
                                moves.append(Move(r, c, r2, c2, p))
                            r2 += dr
                            c2 += dc
        return moves

    def _step_move(self, r, c, p, r2, c2, moves, captures_only):
        if not (0 <= r2 < 8 and 0 <= c2 < 8):
            return
        t = self.board[r2][c2]
        if t:
            if t.isupper() != p.isupper():
                moves.append(Move(r, c, r2, c2, p, t))
        elif not captures_only:
            moves.append(Move(r, c, r2, c2, p))

    def _pawn_moves(self, r, c, p, moves, captures_only):
        b = self.board
        white = p.isupper()
        d = -1 if white else 1
        start_row = 6 if white else 1
        last_row = 0 if white else 7
        promos = "QRBN" if white else "qrbn"

        def add(move):
            if move.er == last_row:
                for pr in promos:
                    moves.append(Move(move.sr, move.sc, move.er, move.ec,
                                      p, move.captured, promo=pr))
            else:
                moves.append(move)

        if not captures_only:
            if b[r + d][c] == "":
                add(Move(r, c, r + d, c, p))
                if r == start_row and b[r + 2 * d][c] == "":
                    moves.append(Move(r, c, r + 2 * d, c, p))
        for dc in (-1, 1):
            c2 = c + dc
            if not 0 <= c2 < 8:
                continue
            t = b[r + d][c2]
            if t and t.isupper() != white:
                add(Move(r, c, r + d, c2, p, t))
            elif self.ep == (r + d, c2):
                captured = "p" if white else "P"
                moves.append(Move(r, c, r + d, c2, p, captured, is_ep=True))

    def _castle_moves(self, r, c, p, moves):
        white = p.isupper()
        if (r, c) != ((7, 4) if white else (0, 4)):
            return
        b = self.board
        rights = ("K", "Q") if white else ("k", "q")
        enemy = not white
        if self.square_attacked(r, 4, enemy):
            return
        if rights[0] in self.castling and b[r][5] == "" and b[r][6] == "":
            if not self.square_attacked(r, 5, enemy) and not self.square_attacked(r, 6, enemy):
                moves.append(Move(r, 4, r, 6, p, is_castle=True))
        if rights[1] in self.castling and b[r][1] == "" and b[r][2] == "" and b[r][3] == "":
            if not self.square_attacked(r, 3, enemy) and not self.square_attacked(r, 2, enemy):
                moves.append(Move(r, 4, r, 2, p, is_castle=True))

    def legal_moves(self, captures_only=False):
        """Coups strictement legaux (le roi ne reste pas en echec)."""
        mover_white = self.white_to_move
        legal = []
        for m in self.generate_pseudo(captures_only):
            self.make_move(m)
            if not self.in_check(mover_white):
                legal.append(m)
            self.unmake_move()
        return legal

    def find_move(self, uci):
        """Retrouve un coup legal a partir de sa notation UCI ('e2e4', 'a7a8q')."""
        for m in self.legal_moves():
            if m.uci() == uci:
                return m
        return None

    # ------------------------------------------------------------ fin de partie
    def insufficient_material(self):
        minor_squares = []
        for r in range(8):
            for c in range(8):
                p = self.board[r][c]
                if not p or p in ("K", "k"):
                    continue
                if p in ("P", "p", "R", "r", "Q", "q"):
                    return False
                minor_squares.append((p, r, c))
        if len(minor_squares) <= 1:
            return True
        if len(minor_squares) == 2:
            (p1, r1, c1), (p2, r2, c2) = minor_squares
            # deux fous de meme couleur de case, camps opposes
            if p1.upper() == "B" and p2.upper() == "B" and p1 != p2:
                return (r1 + c1) % 2 == (r2 + c2) % 2
        return False

    def result(self):
        """None si la partie continue, sinon (score, raison)."""
        if not self.legal_moves():
            if self.in_check(self.white_to_move):
                return ("0-1", "Echec et mat") if self.white_to_move else ("1-0", "Echec et mat")
            return ("1/2-1/2", "Pat")
        if self.halfmove >= 100:
            return ("1/2-1/2", "Regle des 50 coups")
        if self.rep.get(self.key, 0) >= 3:
            return ("1/2-1/2", "Triple repetition")
        if self.insufficient_material():
            return ("1/2-1/2", "Materiel insuffisant")
        return None


def perft(gs, depth):
    """Comptage de noeuds pour valider la generation de coups."""
    if depth == 0:
        return 1
    total = 0
    mover_white = gs.white_to_move
    for m in gs.generate_pseudo():
        gs.make_move(m)
        if not gs.in_check(mover_white):
            total += perft(gs, depth - 1)
        gs.unmake_move()
    return total
