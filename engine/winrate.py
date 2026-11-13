import math
from core.rules import BOARD_SIZE, EMPTY, BLACK, WHITE

DIRS = ((0, 1), (1, 0), (1, 1), (1, -1))


class WinrateEvaluator:
    @staticmethod
    def evaluate_black_winrate(grid, next_turn_color: int, search_eval_from_black: float,
                               rule_mode: str, is_proven_win_color: int = EMPTY) -> float:
        """
        이씬(Yixin) 스타일 정밀 중립 승률 평가기:
        - 실제 5목, VCF/VCT 필승, 또는 수읽기 강제 필승(>= 90,000점) 증명 시에만 100.0% / 0.0%
        - 막히는 단발성 4목(단사)으로 인해 승률이 90%로 뻥튀기되는 현상을 방지하고,
          킬각이 없는 공방전에서는 50% ~ 68% 내외의 현실적이고 묵직한 판세를 출력함.
        """
        if is_proven_win_color == BLACK or search_eval_from_black >= 90_000.0:
            return 1.0
        if is_proven_win_color == WHITE or search_eval_from_black <= -90_000.0:
            return 0.0

        is_free = (rule_mode == "freestyle")
        black_str = WinrateEvaluator._scan_player_strength(grid, BLACK, next_turn_color, is_free)
        white_str = WinrateEvaluator._scan_player_strength(grid, WHITE, next_turn_color, is_free)

        if black_str >= 900_000.0:
            return 1.0
        if white_str >= 900_000.0:
            return 0.0

        # 다음 착수권(선공 템포)에 미세 가중치(6%)만 부여
        if next_turn_color == BLACK:
            black_str *= 1.06
        else:
            white_str *= 1.06

        static_balance = black_str - white_str

        # 필승(80,000+)이 아닌 일반 탐색 점수는 과도한 쏠림 방지를 위해 완만하게 압축 반영
        if abs(search_eval_from_black) < 75_000.0:
            clamped_search = max(-14000.0, min(14000.0, search_eval_from_black * 0.55))
        else:
            clamped_search = max(-45000.0, min(45000.0, search_eval_from_black))

        combined = (static_balance * 0.50) + (clamped_search * 0.50)

        # 스케일 분모를 16,000으로 넓혀, 킬각이 없는 초반/중반 우세에서 90%로 튀지 않게 안정화
        wr = 1.0 / (1.0 + math.exp(-combined / 16000.0))
        return max(0.005, min(0.995, wr))

    @staticmethod
    def _scan_player_strength(grid, color: int, next_turn_color: int, is_free: bool) -> float:
        total = 0.0
        visited = set()
        single_fours = 0
        open_threes = 0

        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if grid[r][c] != color:
                    continue

                center_bonus = max(0, 14 - (abs(r - 7) + abs(c - 7))) * 3.0
                total += center_bonus

                for d_idx, (dr, dc) in enumerate(DIRS):
                    pr, pc = r - dr, c - dc
                    if 0 <= pr < BOARD_SIZE and 0 <= pc < BOARD_SIZE and grid[pr][pc] == color:
                        continue

                    seg_key = (r, c, d_idx)
                    if seg_key in visited:
                        continue
                    visited.add(seg_key)

                    cnt = 1
                    nr, nc = r + dr, c + dc
                    while 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE and grid[nr][nc] == color:
                        cnt += 1
                        nr += dr
                        nc += dc

                    open_ends = 0
                    space_fwd = 0
                    tr, tc = nr, nc
                    while 0 <= tr < BOARD_SIZE and 0 <= tc < BOARD_SIZE and grid[tr][tc] == EMPTY and space_fwd < 4:
                        space_fwd += 1
                        tr += dr
                        tc += dc
                    if space_fwd > 0:
                        open_ends += 1

                    space_bwd = 0
                    tr, tc = r - dr, c - dc
                    while 0 <= tr < BOARD_SIZE and 0 <= tc < BOARD_SIZE and grid[tr][tc] == EMPTY and space_bwd < 4:
                        space_bwd += 1
                        tr -= dr
                        tc -= dc
                    if space_bwd > 0:
                        open_ends += 1

                    # 5목을 만들 물리적 공간이 막힌 죽은 돌(Dead Segment)은 0점 처리
                    if cnt + space_fwd + space_bwd < 5:
                        continue

                    if cnt >= 5:
                        if not is_free and color == BLACK and cnt >= 6:
                            total -= 10000.0
                        else:
                            return 1_000_000.0
                    elif cnt == 4:
                        if open_ends == 2:
                            total += 65000.0  # 양쪽 열린 활사 (필승)
                        elif open_ends == 1:
                            single_fours += 1
                            # 내 턴이면 즉시 5목이므로 필승급이지만, 상대 턴이면 바로 막힐 단사이므로 거품 제거!
                            if next_turn_color == color:
                                total += 65000.0
                            else:
                                total += 950.0
                    elif cnt == 3:
                        if open_ends == 2:
                            open_threes += 1
                            total += 3200.0 if next_turn_color == color else 1600.0
                        elif open_ends == 1:
                            total += 280.0
                    elif cnt == 2:
                        if open_ends == 2:
                            total += 320.0
                        elif open_ends == 1:
                            total += 50.0

        # 만약 상대 턴이라도 내 단사가 2개 이상(4-4)이거나 단사+활삼(4-3)이 이미 완성된 상태라면 필승 점수 부여
        if single_fours >= 2 or (single_fours >= 1 and open_threes >= 1):
            total += 55000.0

        return total