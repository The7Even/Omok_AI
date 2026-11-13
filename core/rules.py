import numpy as np

BOARD_SIZE = 15
EMPTY = 0
BLACK = 1
WHITE = 2
DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))


class RenjuRules:
    @staticmethod
    def is_valid_move(grid: np.ndarray, r: int, c: int, color: int, rule_mode: str):
        if not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE):
            return False, "범위 초과"
        if grid[r, c] != EMPTY:
            return False, "이미 돌이 놓인 자리"

        if rule_mode in ("renju", "opening_renju") and color == BLACK:
            if RenjuRules.is_forbidden_move(grid, r, c):
                return False, "렌주룰 금수 (3-3, 4-4 또는 장목)"

        return True, ""

    @staticmethod
    def check_win(grid: np.ndarray, r: int, c: int, color: int, rule_mode: str) -> bool:
        for dr, dc in DIRECTIONS:
            count = 1
            nr, nc = r + dr, c + dc
            while 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE and grid[nr, nc] == color:
                count += 1
                nr += dr
                nc += dc
            nr, nc = r - dr, c - dc
            while 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE and grid[nr, nc] == color:
                count += 1
                nr -= dr
                nc -= dc

            if rule_mode == "freestyle":
                if count >= 5:
                    return True
            else:
                if color == BLACK and count == 5:
                    return True
                elif color == WHITE and count >= 5:
                    return True
        return False

    @staticmethod
    def _check_exact_five_at(grid: np.ndarray, r: int, c: int) -> bool:
        for dr, dc in DIRECTIONS:
            count = 1
            for step in (1, -1):
                nr, nc = r + dr * step, c + dc * step
                while 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE and grid[nr, nc] == BLACK:
                    count += 1
                    nr += dr * step
                    nc += dc * step
            if count == 5:
                return True
        return False

    @staticmethod
    def _is_overline_at(grid: np.ndarray, r: int, c: int) -> bool:
        for dr, dc in DIRECTIONS:
            count = 1
            for step in (1, -1):
                nr, nc = r + dr * step, c + dc * step
                while 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE and grid[nr, nc] == BLACK:
                    count += 1
                    nr += dr * step
                    nc += dc * step
            if count >= 6:
                return True
        return False

    @staticmethod
    def _count_fours_in_dir(grid: np.ndarray, r: int, c: int, dr: int, dc: int) -> int:
        four_spots = 0
        for k in range(-4, 5):
            if k == 0:
                continue
            nr, nc = r + dr * k, c + dc * k
            if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE and grid[nr, nc] == EMPTY:
                grid[nr, nc] = BLACK
                cnt = 1
                for step in (1, -1):
                    tr, tc = r + dr * step, c + dc * step
                    while 0 <= tr < BOARD_SIZE and 0 <= tc < BOARD_SIZE and grid[tr, tc] == BLACK:
                        cnt += 1
                        tr += dr * step
                        tc += dc * step
                grid[nr, nc] = EMPTY
                if cnt == 5:
                    four_spots += 1

        if four_spots >= 2:
            cont = 1
            for step in (1, -1):
                tr, tc = r + dr * step, c + dc * step
                while 0 <= tr < BOARD_SIZE and 0 <= tc < BOARD_SIZE and grid[tr, tc] == BLACK:
                    cont += 1
                    tr += dr * step
                    tc += dc * step
            if cont == 4:
                return 1
        return four_spots

    @staticmethod
    def _is_open_three_in_dir(grid: np.ndarray, r: int, c: int, dr: int, dc: int, check_false_forbidden: bool) -> bool:
        if RenjuRules._count_fours_in_dir(grid, r, c, dr, dc) > 0:
            return False

        for k in range(-3, 4):
            if k == 0:
                continue
            nr, nc = r + dr * k, c + dc * k
            if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE and grid[nr, nc] == EMPTY:
                # 거짓 금수 검사는 1단계까지만 수행하여 무한 상호 재귀 원천 차단
                if check_false_forbidden:
                    if RenjuRules._is_forbidden_internal(grid, nr, nc, allow_recursive=False):
                        continue

                grid[nr, nc] = BLACK
                win_spots = 0
                for m in range(-4, 5):
                    mr, mc = r + dr * m, c + dc * m
                    if 0 <= mr < BOARD_SIZE and 0 <= mc < BOARD_SIZE and grid[mr, mc] == EMPTY:
                        grid[mr, mc] = BLACK
                        cnt = 1
                        for step in (1, -1):
                            tr, tc = r + dr * step, c + dc * step
                            while 0 <= tr < BOARD_SIZE and 0 <= tc < BOARD_SIZE and grid[tr, tc] == BLACK:
                                cnt += 1
                                tr += dr * step
                                tc += dc * step
                        grid[mr, mc] = EMPTY
                        if cnt == 5:
                            win_spots += 1
                grid[nr, nc] = EMPTY
                if win_spots >= 2:
                    return True
        return False

    @staticmethod
    def _is_forbidden_internal(grid: np.ndarray, r: int, c: int, allow_recursive: bool) -> bool:
        if grid[r, c] != EMPTY:
            return False

        nearby_black = 0
        r_min = max(0, r - 2)
        r_max = min(BOARD_SIZE, r + 3)
        c_min = max(0, c - 2)
        c_max = min(BOARD_SIZE, c + 3)
        for nr in range(r_min, r_max):
            for nc in range(c_min, c_max):
                if grid[nr, nc] == BLACK:
                    nearby_black += 1
        if nearby_black < 2:
            return False

        grid[r, c] = BLACK

        if RenjuRules._check_exact_five_at(grid, r, c):
            grid[r, c] = EMPTY
            return False

        if RenjuRules._is_overline_at(grid, r, c):
            grid[r, c] = EMPTY
            return True

        total_fours = 0
        total_open_threes = 0

        for dr, dc in DIRECTIONS:
            f = RenjuRules._count_fours_in_dir(grid, r, c, dr, dc)
            total_fours += f
            if f == 0:
                if RenjuRules._is_open_three_in_dir(grid, r, c, dr, dc, allow_recursive):
                    total_open_threes += 1

        grid[r, c] = EMPTY
        return total_fours >= 2 or total_open_threes >= 2

    @staticmethod
    def is_forbidden_move(grid: np.ndarray, r: int, c: int) -> bool:
        return RenjuRules._is_forbidden_internal(grid, r, c, allow_recursive=True)

    @staticmethod
    def get_all_forbidden_points(grid: np.ndarray, current_turn: int, rule_mode: str) -> list:
        if rule_mode not in ("renju", "opening_renju") or current_turn != BLACK:
            return []

        candidates = set()
        black_count = 0
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if grid[r, c] == BLACK:
                    black_count += 1
                    for dr in range(-2, 3):
                        nr = r + dr
                        if 0 <= nr < BOARD_SIZE:
                            for dc in range(-2, 3):
                                nc = c + dc
                                if 0 <= nc < BOARD_SIZE and grid[nr, nc] == EMPTY:
                                    candidates.add((nr, nc))

        if black_count < 3:
            return []

        return [(r, c) for r, c in candidates if RenjuRules.is_forbidden_move(grid, r, c)]