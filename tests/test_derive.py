from ingest.derive import derive_columns, PIECE_VALUES

STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
BARE_KINGS = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"
ENDGAME_ROOKS = "4k3/8/8/8/8/8/R7/4K3 w - - 10 50"
WHITE_DOWN_QUEEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNB1KBNR w KQkq - 0 1"
EP_AVAILABLE = "rnbqkbnr/ppp1pppp/8/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3"
PROMOTED_3_KNIGHTS = "4k3/8/8/8/8/8/NN1N4/4K3 w - - 20 40"
NO_CASTLING = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"


def test_piece_count_starting_position():
    assert derive_columns(STARTING_FEN)["piece_count"] == 32


def test_piece_count_bare_kings():
    assert derive_columns(BARE_KINGS)["piece_count"] == 2


def test_side_to_move():
    assert derive_columns(STARTING_FEN)["side_to_move"] == "w"
    assert derive_columns("4k3/8/8/8/8/8/8/4K3 b - - 0 1")["side_to_move"] == "b"


def test_move_number():
    assert derive_columns(STARTING_FEN)["move_number"] == 1
    assert derive_columns(ENDGAME_ROOKS)["move_number"] == 50


def test_phase_precedence_opening_wins():
    cols = derive_columns(STARTING_FEN)
    assert cols["phase"] == "opening"


def test_phase_endgame_when_move_above_10_and_few_pieces():
    cols = derive_columns(ENDGAME_ROOKS)
    assert cols["phase"] == "endgame"


def test_phase_middlegame():
    fen = "r1bqkb1r/pppp1ppp/2n2n2/4p3/4P3/2N2N2/PPPP1PPP/R1BQKB1R w KQkq - 4 11"
    cols = derive_columns(fen)
    assert cols["phase"] == "middlegame"


def test_material_balance_symmetric():
    assert derive_columns(STARTING_FEN)["material_balance"] == 0


def test_material_balance_white_down_queen():
    assert derive_columns(WHITE_DOWN_QUEEN)["material_balance"] == -PIECE_VALUES["q"]


def test_has_en_passant():
    assert derive_columns(STARTING_FEN)["has_en_passant"] == 0
    assert derive_columns(EP_AVAILABLE)["has_en_passant"] == 1


def test_castling_rights_raw():
    assert derive_columns(STARTING_FEN)["castling_rights"] == "KQkq"
    assert derive_columns(NO_CASTLING)["castling_rights"] == "-"


def test_has_promoted_three_knights():
    assert derive_columns(PROMOTED_3_KNIGHTS)["has_promoted"] == 1


def test_has_not_promoted_in_starting_position():
    assert derive_columns(STARTING_FEN)["has_promoted"] == 0
