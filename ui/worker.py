import time
import random
import threading
from core.board import GomokuBoard
from core.rules import RenjuRules, EMPTY, BLACK, WHITE
from engine.search import GomokuSearchEngine, ZOBRIST_TABLE
from engine.winrate import WinrateEvaluator


class AIWorker:
    """
    실제 대국을 플레이하는 AI 워커:
    - 킬각(5목, VCF, VCT, 캐시된 필승 루트) 발견 시 마커 표기 및 일반 연산을 건너뛰고 즉시 착수!
    - 10단계 기준 최대 10~15초 내외의 PVS 심층 수읽기 수행, 하위 단계는 깊이/노드 비례 자연 축소
    """
    def __init__(self, board: GomokuBoard, difficulty: int, ai_color: int):
        self.np_snapshot = board.grid.copy()
        self.grid_list = [row[:] for row in board.grid.tolist()]
        self.rule_mode = board.rule_mode
        self.difficulty = difficulty
        self.ai_color = ai_color

        self._is_running = True
        self._thread = None
        self._lock = threading.Lock()

        self.latest_progress = None  # (visual_list, depth, nodes, nps, black_wr)
        self.final_move = None
        self.is_finished = False

    def start(self):
        self._is_running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def isRunning(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self):
        self._is_running = False

    def wait(self, timeout=0.3):
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def _finish_immediately_with_kill_move(self, r: int, c: int):
        """확실한 킬각 발견 시 원형 마커 표기 없이 즉시 착수!"""
        b_wr = 1.0 if self.ai_color == BLACK else 0.0
        with self._lock:
            self.latest_progress = ([], 0, 1, 10000, b_wr)
            self.final_move = (r, c)
            self.is_finished = True

    def _run(self):
        try:
            start_time = time.time()
            grid = self.grid_list
            np_grid = self.np_snapshot
            rule_mode = self.rule_mode
            opp_color = WHITE if self.ai_color == BLACK else BLACK
            base_hash = GomokuSearchEngine.compute_zobrist_hash(grid)

            # 0. 이전 턴에 이미 계산해 둔 연쇄 킬각 플랜(KILL_PLAN_CACHE)에 현재 국면이 있으면 0.01초 즉시 착수!
            if self.difficulty >= 7 and base_hash in GomokuSearchEngine.KILL_PLAN_CACHE:
                kr, kc = GomokuSearchEngine.KILL_PLAN_CACHE[base_hash]
                if grid[kr][kc] == EMPTY:
                    ok, _ = RenjuRules.is_valid_move(np_grid, kr, kc, self.ai_color, rule_mode)
                    if ok and self._is_running:
                        self._finish_immediately_with_kill_move(kr, kc)
                        return

            candidates = GomokuSearchEngine.get_candidates(grid, radius=2)

            # 1. 내 즉시 5목 승리 수 확인 -> 발견 즉시 마커 없이 착수!
            for r, c in candidates:
                if not self._is_running:
                    return
                ok, _ = RenjuRules.is_valid_move(np_grid, r, c, self.ai_color, rule_mode)
                if not ok:
                    continue
                if GomokuSearchEngine.is_winning_move(np_grid, r, c, self.ai_color, rule_mode):
                    self._finish_immediately_with_kill_move(r, c)
                    return

            # 2. 7단계 이상 AI: 연쇄 공격 킬각(VCF + VCT) 탐색 -> 발견 즉시 연산 건너뛰고 바로 착수!
            if self.difficulty >= 7 and self._is_running:
                if self.difficulty >= 9:
                    kill_move = GomokuSearchEngine.find_vct_kill_move(grid, self.ai_color, rule_mode, max_vct_depth=8)
                else:
                    kill_move = GomokuSearchEngine.find_vcf_win(
                        grid, self.ai_color, rule_mode, max_vcf_depth=10, record_plan=True
                    )
                if kill_move is not None:
                    ok, _ = RenjuRules.is_valid_move(np_grid, kill_move[0], kill_move[1], self.ai_color, rule_mode)
                    if ok and self._is_running:
                        self._finish_immediately_with_kill_move(kill_move[0], kill_move[1])
                        return

            # 3. 5단계 전술 계층 기반 후보군 추출
            ordered_all = GomokuSearchEngine.get_ordered_moves(grid, self.ai_color, rule_mode, limit=12)
            scored_root = []
            for s, r, c in ordered_all:
                if not self._is_running:
                    return
                ok, _ = RenjuRules.is_valid_move(np_grid, r, c, self.ai_color, rule_mode)
                if ok:
                    scored_root.append((s, r, c))

            if not scored_root:
                with self._lock:
                    self.is_finished = True
                return

            # 유일한 강제 방어 수(예: 상대 4목 막기)가 1개뿐이면 지체 없이 즉시 착수
            if len(scored_root) == 1:
                only_r, only_c = scored_root[0][1], scored_root[0][2]
                b_wr = WinrateEvaluator.evaluate_black_winrate(grid, self.ai_color, 0.0, rule_mode)
                with self._lock:
                    self.latest_progress = ([], 1, 1, 5000, b_wr)
                    self.final_move = (only_r, only_c)
                    self.is_finished = True
                return

            # 난이도별 탐색 깊이, 후보 폭, 최대 노드 상한선, 시간 상한선 설정
            # 10단계 기준 약 10~14초 동안 최대 깊이 8, 최대 90,000 노드까지 심층 연산 수행
            config_map = {
                1:  (1, 5,   1500,   3.0),
                2:  (2, 6,   3000,   4.0),
                3:  (2, 7,   5000,   5.0),
                4:  (3, 7,   8000,   6.0),
                5:  (4, 8,  14000,   8.0),
                6:  (4, 9,  20000,   9.0),
                7:  (5, 9,  32000,  11.0),
                8:  (6, 10, 48000,  12.0),
                9:  (7, 10, 68000,  13.5),
                10: (8, 11, 95000,  14.2),
            }
            max_depth, root_limit, max_nodes, hard_time_limit = config_map.get(
                self.difficulty, (4, 8, 15000, 8.0)
            )
            deadline = start_time + hard_time_limit
            top_moves = scored_root[:min(len(scored_root), root_limit)]

            tt_table = {}
            node_counter = [0]
            move_evals = {}
            raw_evals = {}
            nps = 0

            # 기본 초기 선택값 안전 보장
            for prior_s, r, c in top_moves:
                raw_evals[(r, c)] = prior_s * 0.01
                move_evals[(r, c)] = prior_s * 0.01

            for depth in range(1, max_depth + 1):
                if not self._is_running:
                    return
                if node_counter[0] >= max_nodes or time.time() >= deadline:
                    break

                depth_evals = {}
                depth_raw = {}
                visual_list = []
                completed_depth = True

                for prior_s, r, c in top_moves:
                    if not self._is_running:
                        return
                    if node_counter[0] >= max_nodes or time.time() >= deadline:
                        completed_depth = False
                        break

                    grid[r][c] = self.ai_color
                    next_hash = base_hash ^ ZOBRIST_TABLE[r][c][self.ai_color]
                    ev = GomokuSearchEngine.alphabeta_pvs(
                        grid, depth - 1, -1e9, 1e9, False,
                        self.ai_color, rule_mode, (r, c), next_hash, tt_table,
                        node_counter, max_nodes, deadline, lambda: self._is_running
                    )
                    grid[r][c] = EMPTY

                    if not self._is_running or node_counter[0] >= max_nodes or time.time() >= deadline:
                        completed_depth = False
                        break

                    # 수읽기 도중 확실한 필승 수(ev >= 95000)가 증명되면 즉시 연산을 건너뛰고 착수!
                    if ev >= 95000.0 and self.difficulty >= 7:
                        self._finish_immediately_with_kill_move(r, c)
                        return

                    final_ev = ev + min(prior_s * 0.004, 600.0)
                    depth_raw[(r, c)] = final_ev

                    noise_range = max(0, (6 - self.difficulty) * 180)
                    ev_with_noise = final_ev + (random.uniform(-noise_range, noise_range) if noise_range > 0 else 0.0)
                    depth_evals[(r, c)] = ev_with_noise

                    wr = GomokuSearchEngine.score_to_winrate(final_ev)
                    visual_list.append((r, c, wr))

                if completed_depth and depth_evals:
                    raw_evals.update(depth_raw)
                    move_evals.update(depth_evals)

                    elapsed = max(0.001, time.time() - start_time)
                    nps = int(node_counter[0] / elapsed)

                    # AI가 연산하는 동안 찾은 최선의 평가치를 흑/백 중립 판세 승률에도 함께 반영
                    best_ai_ev = max(raw_evals.values())
                    ev_from_black = best_ai_ev if self.ai_color == BLACK else -best_ai_ev
                    b_wr = WinrateEvaluator.evaluate_black_winrate(grid, self.ai_color, ev_from_black, rule_mode)

                    with self._lock:
                        self.latest_progress = (list(visual_list), depth, node_counter[0], nps, b_wr)

                    top_moves.sort(key=lambda item: move_evals.get((item[1], item[2]), -1e9), reverse=True)

            # 4. 7단계 이상 AI: 상위 후보 착수 후 상대에게 VCF 역전을 허용하는지 최종 방어 점검
            if self.difficulty >= 7 and self._is_running and time.time() < deadline + 0.8:
                for _, r, c in top_moves[:4]:
                    if not self._is_running:
                        return
                    grid[r][c] = self.ai_color
                    opp_can_win = GomokuSearchEngine.find_vcf_win(
                        grid, opp_color, rule_mode, max_vcf_depth=8, record_plan=False
                    )
                    grid[r][c] = EMPTY

                    if opp_can_win is not None:
                        raw_evals[(r, c)] = raw_evals.get((r, c), 0.0) - 45000.0
                        move_evals[(r, c)] = move_evals.get((r, c), 0.0) - 45000.0

            final_sorted = sorted(move_evals.items(), key=lambda x: x[1], reverse=True)
            if self.difficulty <= 2 and len(final_sorted) >= 3:
                choice = random.choice(final_sorted[:3])[0]
            elif self.difficulty <= 4 and len(final_sorted) >= 2:
                choice = random.choice(final_sorted[:2])[0]
            else:
                choice = final_sorted[0][0]

            if self._is_running:
                with self._lock:
                    self.final_move = choice
                    self.is_finished = True
        except Exception as e:
            print(f"[AIWorker Error] {e}")
            with self._lock:
                self.is_finished = True


class AnalysisWorker:
    """
    체스닷컴 스타일 중립 백그라운드 분석기:
    - 플레이어 차례일 때만 단독 가동되어 AI 연산 자원을 뺏지 않음
    """
    def __init__(self, board: GomokuBoard):
        self.grid_list = [row[:] for row in board.grid.tolist()]
        self.np_snapshot = board.grid.copy()
        self.next_turn = board.current_turn
        self.rule_mode = board.rule_mode
        self.game_over = board.game_over
        self.winner = board.winner

        self._is_running = True
        self._thread = None
        self._lock = threading.Lock()
        self.latest_analysis = None

    def start(self):
        self._is_running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._is_running = False

    def wait(self, timeout=0.2):
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def _run(self):
        try:
            if self.game_over:
                b_wr = 1.0 if self.winner == BLACK else (0.0 if self.winner == WHITE else 0.5)
                with self._lock:
                    self.latest_analysis = (b_wr, 0, 0, 0)
                return

            grid = self.grid_list
            np_grid = self.np_snapshot
            rule_mode = self.rule_mode
            turn = self.next_turn

            proven_winner = EMPTY
            vcf_win = GomokuSearchEngine.find_vcf_win(grid, turn, rule_mode, max_vcf_depth=10, record_plan=False)
            if vcf_win is not None:
                ok, _ = RenjuRules.is_valid_move(np_grid, vcf_win[0], vcf_win[1], turn, rule_mode)
                if ok:
                    proven_winner = turn

            init_wr = WinrateEvaluator.evaluate_black_winrate(
                grid, turn, 0.0, rule_mode, is_proven_win_color=proven_winner
            )
            with self._lock:
                self.latest_analysis = (init_wr, 0, 1, 0)

            if proven_winner != EMPTY:
                return

            ordered = GomokuSearchEngine.get_ordered_moves(grid, turn, rule_mode, limit=9)
            valid_moves = []
            for s, r, c in ordered:
                ok, _ = RenjuRules.is_valid_move(np_grid, r, c, turn, rule_mode)
                if ok:
                    valid_moves.append((s, r, c))

            if not valid_moves:
                return

            base_hash = GomokuSearchEngine.compute_zobrist_hash(grid)
            tt_table = {}
            node_counter = [0]
            start_time = time.time()
            deadline = start_time + 25.0
            max_ana_nodes = 80000

            prev_ev_from_black = None

            for depth in range(1, 8):
                if not self._is_running or node_counter[0] >= max_ana_nodes or time.time() >= deadline:
                    return

                best_ev_for_turn = -1e9
                move_scores = {}

                for _, r, c in valid_moves:
                    if not self._is_running or node_counter[0] >= max_ana_nodes or time.time() >= deadline:
                        return
                    grid[r][c] = turn
                    next_hash = base_hash ^ ZOBRIST_TABLE[r][c][turn]
                    ev = GomokuSearchEngine.alphabeta_pvs(
                        grid, depth - 1, -1e9, 1e9, False,
                        turn, rule_mode, (r, c), next_hash, tt_table,
                        node_counter, max_ana_nodes, deadline, lambda: self._is_running
                    )
                    grid[r][c] = EMPTY

                    move_scores[(r, c)] = ev
                    if ev > best_ev_for_turn:
                        best_ev_for_turn = ev

                if not self._is_running:
                    return

                ev_from_black = best_ev_for_turn if turn == BLACK else -best_ev_for_turn

                if prev_ev_from_black is not None and abs(ev_from_black) < 90000.0:
                    stabilized_ev = (prev_ev_from_black * 0.5) + (ev_from_black * 0.5)
                else:
                    stabilized_ev = ev_from_black
                prev_ev_from_black = ev_from_black

                black_wr = WinrateEvaluator.evaluate_black_winrate(
                    grid, turn, stabilized_ev, rule_mode, is_proven_win_color=EMPTY
                )

                elapsed = max(0.001, time.time() - start_time)
                nps = int(node_counter[0] / elapsed)

                with self._lock:
                    self.latest_analysis = (black_wr, depth, node_counter[0], nps)

                valid_moves.sort(key=lambda item: move_scores.get((item[1], item[2]), -1e9), reverse=True)
                time.sleep(0.03)
        except Exception as e:
            print(f"[AnalysisWorker Error] {e}")