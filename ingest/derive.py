from __future__ import annotations

PIECE_VALUES: dict[str, int] = {
    "p": 1, "n": 3, "b": 3, "r": 5, "q": 9, "k": 0
}

INITIAL_MAX: dict[str, int] = {
    "p": 8, "n": 2, "b": 2, "r": 2, "q": 1, "k": 1,
}


def _parse_fen(fen: str) -> tuple[str, str, str, str, int, int]:
    parts = fen.strip().split()
    if len(parts) < 6:
        raise ValueError(f"malformed FEN: {fen!r}")
    board, side, castling, ep, halfmove, fullmove = parts[:6]
    return board, side, castling, ep, int(halfmove), int(fullmove)


def _count_pieces(board: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ch in board:
        if ch.isalpha():
            counts[ch] = counts.get(ch, 0) + 1
    return counts


def _material_balance(counts: dict[str, int]) -> int:
    white = sum(PIECE_VALUES[k.lower()] * v for k, v in counts.items() if k.isupper())
    black = sum(PIECE_VALUES[k] * v for k, v in counts.items() if k.islower())
    return white - black


def _has_promoted(counts: dict[str, int]) -> bool:
    for piece, max_count in INITIAL_MAX.items():
        if counts.get(piece.upper(), 0) > max_count:
            return True
        if counts.get(piece, 0) > max_count:
            return True
    return False


def derive_columns(fen: str) -> dict[str, object]:
    board, side, castling, ep, _halfmove, fullmove = _parse_fen(fen)
    counts = _count_pieces(board)
    piece_count = sum(counts.values())

    if fullmove <= 10:
        phase = "opening"
    elif piece_count <= 10:
        phase = "endgame"
    else:
        phase = "middlegame"

    return {
        "piece_count": piece_count,
        "move_number": fullmove,
        "side_to_move": side,
        "phase": phase,
        "material_balance": _material_balance(counts),
        "has_promoted": 1 if _has_promoted(counts) else 0,
        "has_en_passant": 0 if ep == "-" else 1,
        "castling_rights": castling,
    }
