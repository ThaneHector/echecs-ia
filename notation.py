"""Notation algebrique (SAN), export et import PGN."""

import re

from engine import FILES, GameState, sq_name


def san(gs, move, legal=None):
    """Notation algebrique standard d'un coup, calculee AVANT de le jouer.

    `legal` permet de fournir la liste des coups legaux deja calculee.
    """
    if move.is_castle:
        text = "O-O" if move.ec == 6 else "O-O-O"
    else:
        pt = move.piece.upper()
        if pt == "P":
            text = FILES[move.sc] + "x" if move.captured else ""
            text += sq_name(move.er, move.ec)
            if move.promo:
                text += "=" + move.promo.upper()
        else:
            text = pt
            # desambiguisation : autres pieces identiques atteignant la meme case
            if legal is None:
                legal = gs.legal_moves()
            others = [m for m in legal
                      if m.piece == move.piece and (m.er, m.ec) == (move.er, move.ec)
                      and (m.sr, m.sc) != (move.sr, move.sc)]
            if others:
                same_file = any(m.sc == move.sc for m in others)
                same_rank = any(m.sr == move.sr for m in others)
                if not same_file:
                    text += FILES[move.sc]
                elif not same_rank:
                    text += str(8 - move.sr)
                else:
                    text += sq_name(move.sr, move.sc)
            if move.captured:
                text += "x"
            text += sq_name(move.er, move.ec)

    # suffixe echec / mat
    gs.make_move(move)
    if gs.in_check(gs.white_to_move):
        text += "#" if not gs.legal_moves() else "+"
    gs.unmake_move()
    return text


def parse_san(gs, text):
    """Retrouve le coup legal correspondant a une notation SAN, sinon None."""
    cleaned = text.strip().rstrip("+#!?").replace("0-0-0", "O-O-O").replace("0-0", "O-O")
    legal = gs.legal_moves()
    for m in legal:
        if san(gs, m, legal).rstrip("+#") == cleaned:
            return m
    return None


def moves_to_san(moves, start_fen=None):
    """Convertit une liste de coups (depuis la position de depart) en SAN."""
    gs = GameState(start_fen) if start_fen else GameState()
    out = []
    for m in moves:
        mm = gs.find_move(m.uci() if hasattr(m, "uci") else m)
        out.append(san(gs, mm))
        gs.make_move(mm)
    return out


def export_pgn(gs, white="Joueur", black="IA", result=None, date=None, event="Partie ALOGA"):
    """Exporte la partie courante (move_log complet) au format PGN."""
    import datetime
    if date is None:
        date = datetime.date.today().strftime("%Y.%m.%d")
    if result is None:
        r = gs.result()
        result = r[0] if r else "*"

    # rejoue la partie depuis le debut pour produire les SAN
    replay = GameState()
    tokens = []
    for i, m in enumerate(gs.move_log):
        if i % 2 == 0:
            tokens.append(f"{i // 2 + 1}.")
        tokens.append(san(replay, replay.find_move(m.uci())))
        replay.make_move(replay.find_move(m.uci()))
    tokens.append(result)

    headers = [f'[Event "{event}"]', '[Site "ALOGA"]', f'[Date "{date}"]',
               '[Round "1"]', f'[White "{white}"]', f'[Black "{black}"]',
               f'[Result "{result}"]']
    # lignes de coups limitees a ~80 caracteres
    lines, line = [], ""
    for t in tokens:
        if len(line) + len(t) + 1 > 80:
            lines.append(line)
            line = t
        else:
            line = t if not line else line + " " + t
    if line:
        lines.append(line)
    return "\n".join(headers) + "\n\n" + "\n".join(lines) + "\n"


def import_pgn(text):
    """Importe une partie PGN (variante principale). Retourne (GameState, en-tetes)."""
    headers = dict(re.findall(r'\[(\w+)\s+"([^"]*)"\]', text))
    body = re.sub(r'\[[^\]]*\]', ' ', text)          # retire les en-tetes
    body = re.sub(r'\{[^}]*\}', ' ', body)           # retire les commentaires
    # retire les variantes entre parentheses (imbrications comprises)
    while "(" in body:
        body = re.sub(r'\([^()]*\)', ' ', body)
    body = re.sub(r'\$\d+', ' ', body)               # annotations numeriques
    body = re.sub(r'\d+\.(\.\.)?', ' ', body)        # numeros de coups

    gs = GameState(headers["FEN"]) if headers.get("FEN") else GameState()
    for token in body.split():
        if token in ("1-0", "0-1", "1/2-1/2", "*"):
            break
        m = parse_san(gs, token)
        if m is None:
            raise ValueError(f"Coup PGN invalide : {token!r}")
        gs.make_move(m)
    return gs, headers
