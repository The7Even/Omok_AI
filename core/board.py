import random
import numpy as np
from core.rules import RenjuRules, BOARD_SIZE, EMPTY, BLACK, WHITE

# 26주형 전체 데이터 (간접 13주형 + 직접 13주형, 천원=(7,7))
OPENING_26_PATTERNS = [
    # 간접 주형 (13종)
    ("장성 (Long Star)", [(7, 7), (6, 8), (5, 9)]),
    ("협성 (Canyon Star)", [(7, 7), (6, 8), (6, 9)]),
    ("항성 (Steady Star)", [(7, 7), (6, 8), (7, 9)]),
    ("수성 (Water Star)", [(7, 7), (6, 8), (8, 9)]),
    ("유성 (Meteor)", [(7, 7), (6, 8), (9, 9)]),
    ("운월 (Cloud Moon)", [(7, 7), (6, 8), (5, 8)]),
    ("우월 (Rain Moon)", [(7, 7), (6, 8), (7, 8)]),
    ("계월 (Valley Moon)", [(7, 7), (6, 8), (8, 8)]),
    ("산월 (Mountain Moon)", [(7, 7), (6, 8), (9, 8)]),
    ("풍월 (Wind Moon)", [(7, 7), (6, 8), (5, 7)]),
    ("화월 (Flower Moon)", [(7, 7), (6, 8), (6, 7)]),
    ("포월 (Cannon Moon)", [(7, 7), (6, 8), (8, 7)]),
    ("명월 (Bright Moon)", [(7, 7), (6, 8), (9, 7)]),
    # 직접 주형 (13종)
    ("한성 (Cold Star)", [(7, 7), (7, 8), (7, 9)]),
    ("계성 (Stream Star)", [(7, 7), (7, 8), (6, 9)]),
    ("서성 (Auspicious Star)", [(7, 7), (7, 8), (5, 9)]),
    ("금성 (Gold Star)", [(7, 7), (7, 8), (6, 8)]),
    ("송월 (Pine Moon)", [(7, 7), (7, 8), (5, 8)]),
    ("구월 (Hill Moon)", [(7, 7), (7, 8), (6, 7)]),
    ("신월 (New Moon)", [(7, 7), (7, 8), (5, 7)]),
    ("난월 (Orchid Moon)", [(7, 7), (7, 8), (6, 6)]),
    ("은월 (Silver Moon)", [(7, 7), (7, 8), (5, 6)]),
    ("명성 (Bright Star)", [(7, 7), (7, 8), (7, 6)]),
    ("사월 (Slanted Moon)", [(7, 7), (7, 8), (6, 5)]),
    ("혜성 (Comet)", [(7, 7), (7, 8), (7, 5)]),
    ("유월 (Floating Moon)", [(7, 7), (7, 8), (5, 5)]),
]


class GomokuBoard:
    def __init__(self, rule_mode: str = "renju"):
        self.rule_mode = rule_mode
        self.reset()

    def reset(self):
        self.grid = np.zeros((BOARD_SIZE, BOARD_SIZE), dtype=int)
        self.history = []
        self.current_turn = BLACK
        self.game_over = False
        self.winner = None

        self.opening_state = "PLAYING"
        self.opening_name = ""
        self.offer5_candidates = []
        self.forbidden_points = []

        if self.rule_mode == "opening_renju":
            self.setup_opening_renju()
        else:
            self.refresh_forbidden_points()

    def refresh_forbidden_points(self):
        if self.game_over or self.opening_state == "CHOOSE5":
            self.forbidden_points = []
        else:
            self.forbidden_points = RenjuRules.get_all_forbidden_points(
                self.grid, self.current_turn, self.rule_mode
            )

    def setup_opening_renju(self):
        name, moves = random.choice(OPENING_26_PATTERNS)
        self.opening_name = name
        colors = [BLACK, WHITE, BLACK]
        for (r, c), col in zip(moves, colors):
            self.grid[r, c] = col
            self.history.append((r, c, col))
        self.current_turn = WHITE
        self.opening_state = "SWAP1"
        self.refresh_forbidden_points()

    def is_valid_move(self, r: int, c: int, color: int):
        return RenjuRules.is_valid_move(self.grid, r, c, color, self.rule_mode)

    def place_stone(self, r: int, c: int) -> bool:
        if self.game_over:
            return False

        # 오프닝 5수 후보 2곳 제시 단계
        if self.opening_state == "OFFER5":
            if self.grid[r, c] == EMPTY and (r, c) not in self.offer5_candidates:
                valid, _ = self.is_valid_move(r, c, BLACK)
                if not valid:
                    return False
                self.offer5_candidates.append((r, c))
                if len(self.offer5_candidates) == 2:
                    self.opening_state = "CHOOSE5"
                    self.current_turn = WHITE
                self.refresh_forbidden_points()
                return True
            return False

        # 오프닝 5수 최종 선택 단계
        if self.opening_state == "CHOOSE5":
            if (r, c) in self.offer5_candidates:
                self.grid[r, c] = BLACK
                self.history.append((r, c, BLACK))
                self.offer5_candidates.clear()
                self.opening_state = "PLAYING"
                self.current_turn = WHITE
                self.refresh_forbidden_points()
                return True
            return False

        # 일반 착수 및 4수 착수
        valid, _ = self.is_valid_move(r, c, self.current_turn)
        if not valid:
            return False

        self.grid[r, c] = self.current_turn
        self.history.append((r, c, self.current_turn))

        if self.opening_state in ("SWAP1", "MOVE4"):
            self.opening_state = "SWAP2"
            self.current_turn = BLACK
            self.refresh_forbidden_points()
            return True

        if RenjuRules.check_win(self.grid, r, c, self.current_turn, self.rule_mode):
            self.game_over = True
            self.winner = self.current_turn
            self.forbidden_points = []
            return True

        if len(self.history) == BOARD_SIZE * BOARD_SIZE:
            self.game_over = True
            self.winner = 0
            self.forbidden_points = []
            return True

        self.current_turn = WHITE if self.current_turn == BLACK else BLACK
        self.refresh_forbidden_points()
        return True