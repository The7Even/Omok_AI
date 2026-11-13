import math
import time
import random
import numpy as np
from core.rules import RenjuRules, BOARD_SIZE, EMPTY, BLACK, WHITE

_rng = random.Random(20261113)
ZOBRIST_TABLE = [
    [[_rng.getrandbits(63) for _ in range(3)] for _ in range(BOARD_SIZE)]
    for _ in range(BOARD_SIZE)
]

DIRS = ((0, 1), (1, 0), (1, 1), (1, -1))

# 9칸 라인 패턴 고속 룩업 캐시
LINE_MECHANICS_CACHE = {}


def warmup_engine():
    LINE_MECHANICS_CACHE.clear()


class GomokuSearchEngine:
    KILL_PLAN_CACHE = {}

    @staticmethod
    def compute_zobrist_hash(grid) -> int:
        h = 0
        for r in range(BOARD_SIZE):
            row = grid[r]
            for c in range(BOARD_SIZE):
                v = row[c]
                if v != EMPTY:
                    h ^= ZOBRIST_TABLE[r][c][v]
        return h

    @staticmethod
    def get_candidates(grid, radius: int = 2) -> list:
        candidates = set()
        has_stone = False
        for r in range(BOARD_SIZE):
            row = grid[r]
            for c in range(BOARD_SIZE):
                if row[c] != EMPTY:
                    has_stone = True
                    r0 = r - radius if r - radius > 0 else 0
                    r1 = r + radius + 1 if r + radius + 1 < BOARD_SIZE else BOARD_SIZE
                    c0 = c - radius if c - radius > 0 else 0
                    c1 = c + radius + 1 if c + radius + 1 < BOARD_SIZE else BOARD_SIZE
                    for nr in range(r0, r1):
                        nrow = grid[nr]
                        for nc in range(c0, c1):
                            if nrow[nc] == EMPTY:
                                candidates.add((nr, nc))
        if not has_stone:
            return [(7, 7)]
        return list(candidates)

    @staticmethod
    def check_win_fast(grid, r: int, c: int, color: int, is_freestyle: bool) -> bool:
        for dr, dc in DIRS:
            count = 1
            nr, nc = r + dr, c + dc
            while 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE and grid[nr][nc] == color:
                count += 1
                nr += dr
                nc += dc

            nr, nc = r - dr, c - dc
            while 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE and grid[nr][nc] == color:
                count += 1
                nr -= dr
                nc -= dc

            if is_freestyle:
                if count >= 5:
                    return True
            else:
                if color == BLACK and count == 5:
                    return True
                elif color == WHITE and count >= 5:
                    return True
        return False

    @staticmethod
    def is_winning_move(grid: np.ndarray, r: int, c: int, color: int, rule_mode: str) -> bool:
        grid[r, c] = color
        won = RenjuRules.check_win(grid, r, c, color, rule_mode)
        grid[r, c] = EMPTY
        return won

    @staticmethod
    def _eval_single_line_pattern(line_tuple: tuple, color: int, is_freestyle: bool) -> tuple:
        """
        길이 9짜리 1차원 라인을 분석해:
        (axis_score, is_five, is_overline, is_strict_open_four, five_offsets, has_open_three, is_open_two) 반환.
        - is_strict_open_four: 이 수(인덱스 4)를 두었을 때 양쪽이 열린 진짜 연속 활사(_ ● ● ● ● _)가 완성되는지 여부!
          (열린 3의 바로 양옆 끝점 또는 뜀삼의 내부 혈점만 True가 되며, 한 칸 띄운 자리는 절대 True가 되지 않음!)
        """
        cache_key = (line_tuple, color, is_freestyle)
        cached = LINE_MECHANICS_CACHE.get(cache_key)
        if cached is not None:
            return cached

        # 1) 중심(인덱스 4) 기준 연속된 돌 개수 및 직결 양끝 열림 확인
        cnt = 1
        ir = 5
        while ir < 9 and line_tuple[ir] == color:
            cnt += 1
            ir += 1
        il = 3
        while il >= 0 and line_tuple[il] == color:
            cnt += 1
            il -= 1

        if cnt >= 5:
            if not is_freestyle and color == BLACK and cnt >= 6:
                res = (-60000.0, False, True, False, (), False, False)
            else:
                res = (100000.0, True, False, False, (), False, False)
            LINE_MECHANICS_CACHE[cache_key] = res
            return res

        r_open = (ir < 9 and line_tuple[ir] == EMPTY)
        l_open = (il >= 0 and line_tuple[il] == EMPTY)

        # 진짜 연속 활사(_ ● ● ● ● _) 완성 여부:
        # 중심(4)에 두었을 때 정확히 연속 4개가 되고 바로 양끝(il, ir)이 모두 비어있는 경우!
        is_strict_open_four = False
        if cnt == 4 and r_open and l_open:
            if not is_freestyle and color == BLACK:
                # 흑 장목(6목) 금수 예외 확인
                b_over = (il - 1 >= 0 and line_tuple[il - 1] == color)
                a_over = (ir + 1 < 9 and line_tuple[ir + 1] == color)
                if not b_over and not a_over:
                    is_strict_open_four = True
            else:
                is_strict_open_four = True

        # 2) 길이 5 윈도우(start = 0..4) 스캔 -> '내 돌 4개 + 빈칸 1개'이면 4목(단사/뜀사/활사)
        five_offsets = []
        for start in range(5):
            c_cnt = 0
            empty_idx = -1
            blocked = False
            for i in range(start, start + 5):
                v = line_tuple[i]
                if v == color:
                    c_cnt += 1
                elif v == EMPTY:
                    empty_idx = i
                else:
                    blocked = True
                    break
            if not blocked and c_cnt == 4 and empty_idx != -1:
                if not is_freestyle and color == BLACK:
                    b_idx = start - 1
                    a_idx = start + 5
                    if (b_idx >= 0 and line_tuple[b_idx] == color) or (a_idx < 9 and line_tuple[a_idx] == color):
                        continue
                offset = empty_idx - 4
                if offset not in five_offsets:
                    five_offsets.append(offset)

        # 3) 길이 6 윈도우(start = 0..3) 스캔 -> '_ (내 돌 3개 + 빈칸 1개) _'이면 진짜 열린 3(활삼/뜀삼)
        has_open_three = False
        if not five_offsets:
            for start in range(4):
                if line_tuple[start] != EMPTY or line_tuple[start + 5] != EMPTY:
                    continue
                if not (start + 1 <= 4 <= start + 4):
                    continue
                c_cnt = 0
                inner_empty_idx = -1
                blocked = False
                for i in range(start + 1, start + 5):
                    v = line_tuple[i]
                    if v == color:
                        c_cnt += 1
                    elif v == EMPTY:
                        inner_empty_idx = i
                    else:
                        blocked = True
                        break
                if not blocked and c_cnt == 3 and inner_empty_idx != -1:
                    if not is_freestyle and color == BLACK:
                        b_idx = start - 1
                        a_idx = start + 6
                        if (b_idx >= 0 and line_tuple[b_idx] == color) or (a_idx < 9 and line_tuple[a_idx] == color):
                            continue
                    has_open_three = True
                    break

        # 4) 열린 2목(연속 2목 또는 한 칸 띈 2목) 판별 -> 초반 1-3-5 'ㄴ'자 교차 포석 감지에 사용!
        is_open_two = False
        if not five_offsets and not has_open_three:
            if cnt == 2 and r_open and l_open:
                is_open_two = True
            else:
                # _ ● _ ● _ 형태의 띈 열린 2목 확인
                for start in range(1, 4):
                    if line_tuple[start] == EMPTY and line_tuple[start + 4] == EMPTY:
                        sub = line_tuple[start + 1:start + 4]
                        if sub.count(color) == 2 and sub.count(EMPTY) == 1:
                            is_open_two = True
                            break

        axis_score = 0.0
        if is_strict_open_four or len(five_offsets) >= 2:
            axis_score = 26000.0  # 활사
        elif len(five_offsets) == 1:
            axis_score = 3500.0   # 단사 (선수 4목)
        elif has_open_three:
            axis_score = 3100.0   # 활삼 / 활뜀삼
        elif is_open_two:
            axis_score = 320.0    # 열린 2목
        else:
            open_cnt = (1 if r_open else 0) + (1 if l_open else 0)
            if cnt == 3 and open_cnt == 1:
                axis_score = 380.0
            elif cnt == 2 and open_cnt == 1:
                axis_score = 60.0

        res = (
            axis_score,
            False,
            False,
            is_strict_open_four,
            tuple(five_offsets),
            has_open_three,
            is_open_two,
        )
        if len(LINE_MECHANICS_CACHE) < 120000:
            LINE_MECHANICS_CACHE[cache_key] = res
        return res

    @staticmethod
    def analyze_move_mechanics(grid, r: int, c: int, color: int, is_freestyle: bool) -> tuple:
        """
        고속 캐시 기반 (r, c) 착수 역학 분석:
        반환값: (score, win_now, five_spots_list, is_direct_open_four, open_three_axis_count)
        """
        score = 0.0
        five_spots = []
        is_direct_open_four = False
        open_three_axes = 0
        open_two_axes = 0

        for dr, dc in DIRS:
            line = [0] * 9
            for k in range(-4, 5):
                idx = k + 4
                if k == 0:
                    line[idx] = color
                else:
                    nr, nc = r + dr * k, c + dc * k
                    if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
                        line[idx] = grid[nr][nc]
                    else:
                        line[idx] = -1

            ax_score, is_five, is_overline, strict_o4, f_offs, has_o3, is_o2 = (
                GomokuSearchEngine._eval_single_line_pattern(tuple(line), color, is_freestyle)
            )
            if is_overline:
                return -60000.0, False, [], False, 0
            if is_five:
                return 100000.0, True, [], False, 0

            score += ax_score
            if strict_o4:
                is_direct_open_four = True
            for off in f_offs:
                spot = (r + dr * off, c + dc * off)
                if spot not in five_spots:
                    five_spots.append(spot)
            if has_o3:
                open_three_axes += 1
            if is_o2:
                open_two_axes += 1

        next_five_cnt = len(five_spots)

        # 복합 다중 위협 (4-4, 4-3, 3-3) 판정
        if next_five_cnt >= 2:
            score += 20000.0
        if next_five_cnt >= 1 and open_three_axes >= 1:
            score += 22000.0
        elif open_three_axes >= 2:
            if not is_freestyle and color == BLACK:
                return -60000.0, False, [], False, 0
            score += 18000.0

        # [핵심 추가] 초반 1-3-5 'ㄴ'자(양방향 열린 2목 이상 교차) 시너지 보너스!
        # 상대가 'ㄴ'자 교차 형태를 만들려는 급소를 최우선으로 견제하고, 내 공격 시에도 입체적인 'ㄴ'자 포석을 구축함
        if open_two_axes >= 2:
            score += open_two_axes * 750.0
        elif open_two_axes >= 1 and open_three_axes >= 1:
            score += 950.0

        center_dist = abs(r - 7) + abs(c - 7)
        if center_dist < 14:
            score += (14 - center_dist) * 5.0

        return score, False, five_spots, is_direct_open_four, open_three_axes

    @staticmethod
    def evaluate_point_fast(grid, r: int, c: int, color: int, is_freestyle: bool) -> float:
        score, _, _, _, _ = GomokuSearchEngine.analyze_move_mechanics(grid, r, c, color, is_freestyle)
        return score

    @staticmethod
    def _get_four_moves_and_defenses(grid, attacker: int, is_freestyle: bool) -> list:
        """
        4목 공격 후보들을 추출하되, '즉시 활사/4-3'이 되는 최단 마무리 수를 맨 앞에 배치하여
        20수·24수처럼 불필요하게 돌아가는 현상을 원천 방지!
        """
        immediate_finishers = []
        forcing_fours = []
        cands = GomokuSearchEngine.get_candidates(grid, radius=2)

        for r, c in cands:
            score, win_now, five_spots, is_o4, o3_axes = GomokuSearchEngine.analyze_move_mechanics(
                grid, r, c, attacker, is_freestyle
            )
            if score < -40000.0:
                continue
            if win_now:
                return [((r, c), [], 100000.0)]
            if len(five_spots) >= 2 or is_o4:
                immediate_finishers.append(((r, c), five_spots, score + 50000.0))
            elif len(five_spots) == 1:
                # 단사(4목)이면서 동시에 열린 3을 동반하는 4-3 결정타를 최우선 정렬!
                priority = score + (25000.0 if o3_axes >= 1 else 0.0)
                forcing_fours.append(((r, c), five_spots, priority))

        if immediate_finishers:
            immediate_finishers.sort(key=lambda x: x[2], reverse=True)
            return immediate_finishers[:1]

        forcing_fours.sort(key=lambda x: x[2], reverse=True)
        return forcing_fours

    @staticmethod
    def find_vcf_win(grid, attacker: int, rule_mode: str, max_vcf_depth: int = 10, record_plan: bool = False):
        """
        최단 수순 보장(Shortest-Path IDDFS) 연속 4목(VCF) & 4-3 필승 탐색기:
        깊이 2 -> 4 -> 6 -> 8 -> 10 순으로 탐색하여, 3수 만에 끝나는 4-3 킬각이 있으면
        절대 8~10수짜리 긴 루트로 돌아가지 않고 가장 짧고 간결한 킬각을 즉시 반환함!
        """
        is_free = (rule_mode == "freestyle")
        defender = WHITE if attacker == BLACK else BLACK

        cands_init = GomokuSearchEngine.get_candidates(grid, radius=2)
        opp_immediate_wins = set()
        for r, c in cands_init:
            _, opp_win, _, _, _ = GomokuSearchEngine.analyze_move_mechanics(grid, r, c, defender, is_free)
            if opp_win:
                opp_immediate_wins.add((r, c))

        def dfs_vcf(depth: int, z_hash: int, must_block_set: set, visited: set):
            if depth <= 0 or z_hash in visited:
                return None
            visited.add(z_hash)

            four_list = GomokuSearchEngine._get_four_moves_and_defenses(grid, attacker, is_free)
            for (ar, ac), defenses, _ in four_list:
                if must_block_set and (ar, ac) not in must_block_set and len(defenses) > 0:
                    continue

                # 즉시 5목이거나 양쪽 열린 활사/4-4 완성 -> 최단 종료!
                if len(defenses) == 0 or len(defenses) >= 2:
                    if record_plan:
                        GomokuSearchEngine.KILL_PLAN_CACHE[z_hash] = (ar, ac)
                    return (ar, ac)

                dr, dc = defenses[0]
                grid[ar][ac] = attacker

                # 상대가 유일한 방어점 (dr, dc)를 막았을 때의 상태 확인
                _, def_win, def_fives, def_o4, _ = GomokuSearchEngine.analyze_move_mechanics(
                    grid, dr, dc, defender, is_free
                )
                if def_win or def_o4 or len(def_fives) >= 2:
                    grid[ar][ac] = EMPTY
                    continue

                grid[dr][dc] = defender
                opp_counter_wins = set(def_fives)

                # [핵심] 만약 내 단사(ar, ac)가 4-3 결정타였다면, 상대가 4목을 막은 직후(dr, dc)
                # 나에게 남아있는 열린 3이 다음 턴 즉시 활사(len(defenses)>=2)로 터지므로 depth-2에서 바로 승리 확인됨!
                next_h = z_hash ^ ZOBRIST_TABLE[ar][ac][attacker] ^ ZOBRIST_TABLE[dr][dc][defender]
                sub_win = dfs_vcf(depth - 2, next_h, opp_counter_wins, visited)

                grid[dr][dc] = EMPTY
                grid[ar][ac] = EMPTY

                if sub_win is not None:
                    if record_plan:
                        GomokuSearchEngine.KILL_PLAN_CACHE[z_hash] = (ar, ac)
                    return (ar, ac)

            return None

        init_hash = GomokuSearchEngine.compute_zobrist_hash(grid)
        # 짧은 깊이(2수 = 단사/활사 즉결, 4수 = 단사 1회 후 4-3/활사 마무리)부터 순차 탐색하여 불필요한 우회 원천 차단!
        for d_limit in range(2, max_vcf_depth + 1, 2):
            visited_set = set()
            win_move = dfs_vcf(d_limit, init_hash, opp_immediate_wins, visited_set)
            if win_move is not None:
                return win_move
        return None

    @staticmethod
    def find_vct_kill_move(grid, attacker: int, rule_mode: str, max_vct_depth: int = 8):
        """
        최단 경로 연쇄 공격(VCT) 킬각 탐색기:
        1순위: 짧은 VCF 또는 [단사 1회 -> 상대 강제 응수 -> 4-3 결정타] (예: F9 - H9 - D7/H11)
        2순위: [열린 3 선공 -> 상대 방어 -> 후속 최단 VCF/4-3 마무리]
        """
        # 1) 최단 거리 VCF (2수 ~ 6수 이내의 직결 킬각) 우선 확인
        short_vcf = GomokuSearchEngine.find_vcf_win(grid, attacker, rule_mode, max_vcf_depth=6, record_plan=True)
        if short_vcf is not None:
            return short_vcf

        is_free = (rule_mode == "freestyle")
        defender = WHITE if attacker == BLACK else BLACK
        cands = GomokuSearchEngine.get_candidates(grid, radius=2)

        # 상대에게 당장 5목이나 활사가 있으면 내 열린 3 선공 불가
        for r, c in cands:
            _, opp_win, opp_fives, opp_o4, _ = GomokuSearchEngine.analyze_move_mechanics(grid, r, c, defender, is_free)
            if opp_win or opp_o4 or len(opp_fives) >= 2:
                return GomokuSearchEngine.find_vcf_win(grid, attacker, rule_mode, max_vcf_depth=10, record_plan=True)

        base_hash = GomokuSearchEngine.compute_zobrist_hash(grid)

        # 2) [단사(F9) -> 상대 강제 응수(H9) -> 4-3 포지션(D7/H11) 완성] 3수 킬각 정밀 탐색!
        #    (연속 4목으로 끝까지 안 가도, 단사 1번 쳐놓고 4-3만 만들면 상대는 양쪽을 다 못 막으므로 즉시 필승!)
        four_candidates = GomokuSearchEngine._get_four_moves_and_defenses(grid, attacker, is_free)
        for (ar, ac), defenses, _ in four_candidates[:6]:
            if len(defenses) != 1:
                continue
            dr, dc = defenses[0]
            grid[ar][ac] = attacker
            _, def_win, def_fives, def_o4, _ = GomokuSearchEngine.analyze_move_mechanics(grid, dr, dc, defender, is_free)
            if def_win or def_o4 or len(def_fives) >= 1:
                grid[ar][ac] = EMPTY
                continue

            grid[dr][dc] = defender
            after_def_hash = base_hash ^ ZOBRIST_TABLE[ar][ac][attacker] ^ ZOBRIST_TABLE[dr][dc][defender]

            # 상대가 강제 응수(dr, dc)를 둔 직후, 내가 다음 한 수(D7/H11 등)로 '4-3' 또는 '3-3'을 꽂을 수 있는지 확인!
            follow_cands = GomokuSearchEngine.get_candidates(grid, radius=2)
            killer_followup = None
            for fr, fc in follow_cands:
                fs, fwin, ffives, fo4, fo3_axes = GomokuSearchEngine.analyze_move_mechanics(
                    grid, fr, fc, attacker, is_free
                )
                if fs < -40000.0:
                    continue
                if fwin or fo4 or len(ffives) >= 2 or (len(ffives) >= 1 and fo3_axes >= 1):
                    # 상대에게 그사이 역4목이 없는지 확인 후 4-3 필승 확정!
                    killer_followup = (fr, fc)
                    break

            grid[dr][dc] = EMPTY
            grid[ar][ac] = EMPTY

            if killer_followup is not None:
                GomokuSearchEngine.KILL_PLAN_CACHE[base_hash] = (ar, ac)
                GomokuSearchEngine.KILL_PLAN_CACHE[after_def_hash] = killer_followup
                return (ar, ac)

        # 3) 장기 VCF (8~10수) 확인
        long_vcf = GomokuSearchEngine.find_vcf_win(grid, attacker, rule_mode, max_vcf_depth=10, record_plan=True)
        if long_vcf is not None:
            return long_vcf

        return None

    @staticmethod
    def get_ordered_moves(grid, turn_color: int, rule_mode: str, limit: int = 12) -> list:
        """
        5단계 전술 계층 후보 생성기 (한 칸 띄운 가짜 방어 옵션 완벽 제거!):
        - 상대의 열린 3을 방어할 때, 오직 상대가 두면 '즉시 연속 활사(opp_o4 == True)' 또는 '즉시 4-3'이 되는
          직결 혈점만 true_block_zones에 등록함! (바깥쪽 opp_fives 확장점을 넣던 버그 제거)
        """
        is_free = (rule_mode == "freestyle")
        opp = WHITE if turn_color == BLACK else BLACK
        cands = GomokuSearchEngine.get_candidates(grid, radius=2)

        must_block_five = []
        my_open_fours = []
        my_single_fours = []
        true_block_zones = set()
        scored_cands = []

        for r, c in cands:
            my_s, my_win, my_fives, my_o4, _ = GomokuSearchEngine.analyze_move_mechanics(
                grid, r, c, turn_color, is_free
            )
            if my_s < -40000.0:
                continue
            if my_win:
                return [(1000000.0, r, c)]

            opp_s, opp_win, opp_fives, opp_o4, opp_three_axes = GomokuSearchEngine.analyze_move_mechanics(
                grid, r, c, opp, is_free
            )

            if opp_win:
                must_block_five.append((500000.0 + my_s, r, c))
                continue

            my_five_cnt = len(my_fives)
            if my_o4 or my_five_cnt >= 2:
                my_open_fours.append((300000.0 + my_s, r, c))
            elif my_five_cnt == 1:
                my_single_fours.append((85000.0 + my_s + opp_s * 0.5, r, c))

            # [핵심 교정] 상대가 (r, c)에 두었을 때 '진짜 연속 활사(opp_o4)'가 되거나 '즉시 4-3'이 되는 그 좌표 (r, c)만
            # 직접 방어점으로 추가! (한 칸 더 떨어진 바깥쪽 opp_fives 좌표를 추가하지 않아 '한 칸 띄운 방어' 완전 배제!)
            if opp_o4 or len(opp_fives) >= 2 or (len(opp_fives) >= 1 and opp_three_axes >= 1):
                true_block_zones.add((r, c))

            scored_cands.append((my_s * 1.15 + opp_s, r, c, my_s, opp_s))

        if must_block_five:
            must_block_five.sort(key=lambda x: x[0], reverse=True)
            return must_block_five

        if my_open_fours:
            my_open_fours.sort(key=lambda x: x[0], reverse=True)
            return my_open_fours[:2]

        # 상대 열린 3(다음 턴 활사/4-3 위협)이 있을 때:
        # 오직 [열린 3의 바로 양끝 직결 차단점(true_block_zones)] + [내 4목(단사) 선수 카운터(my_single_fours)] 두 가지만 연산!
        if true_block_zones:
            true_defense_moves = []
            counter_set = {(r, c) for _, r, c in my_single_fours}

            for _, r, c, my_s, opp_s in scored_cands:
                if (r, c) in counter_set:
                    continue
                if (r, c) in true_block_zones:
                    true_defense_moves.append((120000.0 + opp_s * 1.3 + my_s, r, c))

            true_defense_moves.sort(key=lambda x: x[0], reverse=True)
            my_single_fours.sort(key=lambda x: x[0], reverse=True)

            combined_tactical = true_defense_moves + my_single_fours
            if combined_tactical:
                return combined_tactical[:limit]

        scored_cands.sort(key=lambda x: x[0], reverse=True)
        return [(s, r, c) for s, r, c, _, _ in scored_cands[:limit]]

    @staticmethod
    def evaluate_leaf_fast(grid, ai_color: int, opp_color: int,
                           maximizing: bool, is_freestyle: bool) -> float:
        cands = GomokuSearchEngine.get_candidates(grid, radius=2)
        best_ai = 0.0
        second_ai = 0.0
        best_opp = 0.0
        second_opp = 0.0

        ai_open_four_spots = 0
        opp_open_four_spots = 0

        for r, c in cands:
            s_ai, win_ai, fives_ai, o4_ai, threes_ax_ai = GomokuSearchEngine.analyze_move_mechanics(
                grid, r, c, ai_color, is_freestyle
            )
            if win_ai:
                best_ai = max(best_ai, 100000.0)
            else:
                if o4_ai or len(fives_ai) >= 2 or (len(fives_ai) >= 1 and threes_ax_ai >= 1):
                    ai_open_four_spots += 1
                if s_ai > best_ai:
                    second_ai = best_ai
                    best_ai = s_ai
                elif s_ai > second_ai:
                    second_ai = s_ai

            s_opp, win_opp, fives_opp, o4_opp, threes_ax_opp = GomokuSearchEngine.analyze_move_mechanics(
                grid, r, c, opp_color, is_freestyle
            )
            if win_opp:
                best_opp = max(best_opp, 100000.0)
            else:
                if o4_opp or len(fives_opp) >= 2 or (len(fives_opp) >= 1 and threes_ax_opp >= 1):
                    opp_open_four_spots += 1
                if s_opp > best_opp:
                    second_opp = best_opp
                    best_opp = s_opp
                elif s_opp > second_opp:
                    second_opp = s_opp

        if maximizing:
            if best_ai >= 100000.0:
                return 95000.0
            if best_opp >= 100000.0:
                return -90000.0
            if ai_open_four_spots >= 1:
                return 80000.0
            if opp_open_four_spots >= 2:
                return -78000.0
        else:
            if best_opp >= 100000.0:
                return -95000.0
            if best_ai >= 100000.0:
                return 90000.0
            if opp_open_four_spots >= 1:
                return -80000.0
            if ai_open_four_spots >= 2:
                return 78000.0

        ai_total = best_ai + second_ai * 0.35
        opp_total = best_opp + second_opp * 0.35

        if maximizing:
            return ai_total * 1.12 - opp_total
        return ai_total - opp_total * 1.12

    @staticmethod
    def alphabeta_pvs(grid, depth: int, alpha: float, beta: float,
                      maximizing: bool, ai_color: int, rule_mode: str,
                      last_move: tuple, z_hash: int, tt_table: dict,
                      node_counter: list, max_nodes: int, deadline: float,
                      stop_Check) -> float:
        node_counter[0] += 1
        if (node_counter[0] & 63) == 0:
            if not stop_Check() or node_counter[0] >= max_nodes or time.time() >= deadline:
                return 0.0

        is_free = (rule_mode == "freestyle")
        opp = WHITE if ai_color == BLACK else BLACK
        prev_color = opp if maximizing else ai_color

        if last_move is not None:
            lr, lc = last_move
            if GomokuSearchEngine.check_win_fast(grid, lr, lc, prev_color, is_free):
                base_win = 100000.0 + depth * 1500.0
                return -base_win if maximizing else base_win

        orig_alpha = alpha
        tt_key = (z_hash, depth, maximizing)
        cached = tt_table.get(tt_key)
        if cached is not None:
            tt_val, tt_flag = cached
            if tt_flag == 0:
                return tt_val
            elif tt_flag == 1 and tt_val > alpha:
                alpha = tt_val
            elif tt_flag == 2 and tt_val < beta:
                beta = tt_val
            if alpha >= beta:
                return tt_val

        if depth == 0:
            val = GomokuSearchEngine.evaluate_leaf_fast(grid, ai_color, opp, maximizing, is_free)
            tt_table[tt_key] = (val, 0)
            return val

        turn_color = ai_color if maximizing else opp
        branch_limit = 8 if depth >= 4 else (9 if depth >= 2 else 11)
        scored = GomokuSearchEngine.get_ordered_moves(grid, turn_color, rule_mode, limit=branch_limit)

        if not scored:
            return 0.0

        if maximizing:
            max_eval = -1e9
            for idx, (_, r, c) in enumerate(scored):
                grid[r][c] = ai_color
                next_hash = z_hash ^ ZOBRIST_TABLE[r][c][ai_color]

                if idx == 0:
                    ev = GomokuSearchEngine.alphabeta_pvs(
                        grid, depth - 1, alpha, beta, False,
                        ai_color, rule_mode, (r, c), next_hash, tt_table,
                        node_counter, max_nodes, deadline, stop_Check
                    )
                else:
                    ev = GomokuSearchEngine.alphabeta_pvs(
                        grid, depth - 1, alpha, alpha + 1.0, False,
                        ai_color, rule_mode, (r, c), next_hash, tt_table,
                        node_counter, max_nodes, deadline, stop_Check
                    )
                    if alpha < ev < beta and stop_Check() and node_counter[0] < max_nodes and time.time() < deadline:
                        ev = GomokuSearchEngine.alphabeta_pvs(
                            grid, depth - 1, ev, beta, False,
                            ai_color, rule_mode, (r, c), next_hash, tt_table,
                            node_counter, max_nodes, deadline, stop_Check
                        )

                grid[r][c] = EMPTY

                if not stop_Check() or node_counter[0] >= max_nodes or time.time() >= deadline:
                    return max_eval if max_eval > -1e8 else 0.0

                if ev > max_eval:
                    max_eval = ev
                if ev > alpha:
                    alpha = ev
                if beta <= alpha:
                    break

            flag = 2 if max_eval <= orig_alpha else (1 if max_eval >= beta else 0)
            tt_table[tt_key] = (max_eval, flag)
            return max_eval
        else:
            min_eval = 1e9
            for idx, (_, r, c) in enumerate(scored):
                grid[r][c] = opp
                next_hash = z_hash ^ ZOBRIST_TABLE[r][c][opp]

                if idx == 0:
                    ev = GomokuSearchEngine.alphabeta_pvs(
                        grid, depth - 1, alpha, beta, True,
                        ai_color, rule_mode, (r, c), next_hash, tt_table,
                        node_counter, max_nodes, deadline, stop_Check
                    )
                else:
                    ev = GomokuSearchEngine.alphabeta_pvs(
                        grid, depth - 1, beta - 1.0, beta, True,
                        ai_color, rule_mode, (r, c), next_hash, tt_table,
                        node_counter, max_nodes, deadline, stop_Check
                    )
                    if alpha < ev < beta and stop_Check() and node_counter[0] < max_nodes and time.time() < deadline:
                        ev = GomokuSearchEngine.alphabeta_pvs(
                            grid, depth - 1, alpha, ev, True,
                            ai_color, rule_mode, (r, c), next_hash, tt_table,
                            node_counter, max_nodes, deadline, stop_Check
                        )

                grid[r][c] = EMPTY

                if not stop_Check() or node_counter[0] >= max_nodes or time.time() >= deadline:
                    return min_eval if min_eval < 1e8 else 0.0

                if ev < min_eval:
                    min_eval = ev
                if ev < beta:
                    beta = ev
                if beta <= alpha:
                    break

            flag = 2 if min_eval <= orig_alpha else (1 if min_eval >= beta else 0)
            tt_table[tt_key] = (min_eval, flag)
            return min_eval

    @staticmethod
    def score_to_winrate(eval_score: float) -> float:
        if eval_score >= 90000.0:
            return 0.99
        if eval_score <= -90000.0:
            return 0.02
        wr = 1.0 / (1.0 + math.exp(-eval_score / 9500.0))
        return max(0.03, min(0.98, wr))