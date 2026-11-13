import random
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QRadioButton, QButtonGroup,
    QStackedWidget, QFrame, QProgressBar, QMessageBox, QGroupBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from core.board import GomokuBoard
from core.rules import BOARD_SIZE, BLACK, WHITE
from engine.search import GomokuSearchEngine
from ui.board_widget import BoardWidget
from ui.worker import AIWorker, AnalysisWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gomoku AI Engine - 오목 인공지능")
        self.resize(1000, 740)
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #1e1f22; color: #e8eaed; font-family: 'Malgun Gothic', 'Segoe UI'; }
            QPushButton { background-color: #2b2d31; border: 1px solid #3f4147; border-radius: 6px; padding: 10px 16px; font-weight: bold; }
            QPushButton:hover { background-color: #383a40; border-color: #5865f2; }
            QPushButton#PrimaryBtn { background-color: #5865f2; color: white; border: none; font-size: 15px; }
            QPushButton#PrimaryBtn:hover { background-color: #4752c4; }
            QGroupBox { border: 1px solid #3f4147; border-radius: 8px; margin-top: 12px; padding-top: 16px; font-weight: bold; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #949ba4; }
            QRadioButton { spacing: 10px; font-size: 13px; padding: 4px 2px; color: #e8eaed; }
            QRadioButton::indicator { width: 16px; height: 16px; border-radius: 9px; border: 2px solid #80848e; background-color: #1e1f22; }
            QRadioButton::indicator:hover { border-color: #b5bac1; }
            QRadioButton::indicator:checked {
                border: 2px solid #5865f2;
                background-color: qradialgradient(cx:0.5, cy:0.5, radius:0.45, fx:0.5, fy:0.5,
                    stop:0 #ffffff, stop:0.65 #ffffff, stop:0.75 #5865f2, stop:1 #5865f2);
            }
        """)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.ai_worker = None
        self.analysis_worker = None

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(35)
        self.poll_timer.timeout.connect(self.poll_workers)

        self.game_mode = "pve"
        self.difficulty = 5
        self.rule_mode = "renju"
        self.human_color = BLACK
        self.displayed_black_wr = 0.5

        self.init_lobby_ui()
        self.init_game_ui()

    def init_lobby_ui(self):
        lobby = QWidget()
        layout = QVBoxLayout(lobby)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(18)

        title = QLabel("⚫ 오목 AI 대국 플랫폼 ⚪")
        title.setFont(QFont("Malgun Gothic", 24, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        card = QFrame()
        card.setFixedWidth(500)
        card.setStyleSheet("QFrame { background-color: #2b2d31; border-radius: 12px; padding: 16px; }")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(14)

        mode_group = QGroupBox("1. 대전 모드 선택")
        mode_layout = QHBoxLayout(mode_group)
        self.mode_btn_group = QButtonGroup(self)
        self.rb_pvp = QRadioButton("사람 vs 사람 (2인용)")
        self.rb_pve = QRadioButton("사람 vs AI (엔진 대전)")
        self.rb_pve.setChecked(True)
        self.mode_btn_group.addButton(self.rb_pvp)
        self.mode_btn_group.addButton(self.rb_pve)
        mode_layout.addWidget(self.rb_pvp)
        mode_layout.addWidget(self.rb_pve)
        card_layout.addWidget(mode_group)

        self.color_group = QGroupBox("2. 내 돌 색상 선택 (선공/후공)")
        color_layout = QHBoxLayout(self.color_group)
        self.color_btn_group = QButtonGroup(self)
        self.rb_black = QRadioButton("⚫ 흑돌 (선공)")
        self.rb_white = QRadioButton("⚪ 백돌 (후공)")
        self.rb_rand_col = QRadioButton("🎲 랜덤")
        self.rb_black.setChecked(True)
        self.color_btn_group.addButton(self.rb_black)
        self.color_btn_group.addButton(self.rb_white)
        self.color_btn_group.addButton(self.rb_rand_col)
        color_layout.addWidget(self.rb_black)
        color_layout.addWidget(self.rb_white)
        color_layout.addWidget(self.rb_rand_col)
        card_layout.addWidget(self.color_group)

        self.diff_group = QGroupBox("3. AI 난이도 설정 (1단계 ~ 10단계)")
        diff_layout = QVBoxLayout(self.diff_group)
        self.diff_label = QLabel("현재 난이도: 5단계 (중수 - 표준 수읽기)")
        self.diff_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.diff_slider = QSlider(Qt.Orientation.Horizontal)
        self.diff_slider.setRange(1, 10)
        self.diff_slider.setValue(5)
        self.diff_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.diff_slider.setTickInterval(1)
        self.diff_slider.valueChanged.connect(self.on_diff_changed)
        diff_layout.addWidget(self.diff_label)
        diff_layout.addWidget(self.diff_slider)
        card_layout.addWidget(self.diff_group)

        self.rb_pvp.toggled.connect(self.on_mode_toggled)

        rule_group = QGroupBox("4. 경기 규칙 선택")
        rule_layout = QVBoxLayout(rule_group)
        self.rule_btn_group = QButtonGroup(self)
        self.rb_free = QRadioButton("프리룰 (금수 없음, 6목 이상 승리 인정)")
        self.rb_renju = QRadioButton("정통 렌주룰 (흑 3-3, 4-4, 장목 금수)")
        self.rb_opening = QRadioButton("오프닝 렌주 (26주형 + 스왑 + 5수2타)")
        self.rb_renju.setChecked(True)
        self.rule_btn_group.addButton(self.rb_free)
        self.rule_btn_group.addButton(self.rb_renju)
        self.rule_btn_group.addButton(self.rb_opening)
        rule_layout.addWidget(self.rb_free)
        rule_layout.addWidget(self.rb_renju)
        rule_layout.addWidget(self.rb_opening)
        card_layout.addWidget(rule_group)

        start_btn = QPushButton("대국 시작하기")
        start_btn.setObjectName("PrimaryBtn")
        start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        start_btn.clicked.connect(self.start_game)
        card_layout.addWidget(start_btn)

        layout.addWidget(card)
        self.stack.addWidget(lobby)

    def on_mode_toggled(self, pvp_checked: bool):
        self.diff_group.setEnabled(not pvp_checked)
        self.color_group.setEnabled(not pvp_checked)

    def on_diff_changed(self, val: int):
        desc = {
            1: "입문 (초보)", 2: "하수 (기초 방어)", 3: "초급 (패턴 인식)",
            4: "중하수 (위협 감지)", 5: "중수 (표준 수읽기)", 6: "중고수 (심화 탐색)",
            7: "고수 (강력한 공격)", 8: "유단자 (정밀 수읽기)", 9: "사범 (최대 깊이)",
            10: "마스터 (최고 난이도)"
        }
        self.diff_label.setText(f"현재 난이도: {val}단계 ({desc[val]})")

    def init_game_ui(self):
        game_page = QWidget()
        main_layout = QHBoxLayout(game_page)

        self.board = GomokuBoard("renju")
        self.board_widget = BoardWidget(self.board)
        self.board_widget.cell_clicked.connect(self.on_board_clicked)
        main_layout.addWidget(self.board_widget, stretch=3)

        side_panel = QFrame()
        side_panel.setFixedWidth(335)
        side_panel.setStyleSheet("QFrame { background-color: #2b2d31; border-radius: 10px; padding: 12px; }")
        side_layout = QVBoxLayout(side_panel)
        side_layout.setSpacing(14)

        self.info_header = QLabel("대국 정보")
        self.info_header.setFont(QFont("Malgun Gothic", 15, QFont.Weight.Bold))
        side_layout.addWidget(self.info_header)

        self.turn_label = QLabel("현재 차례: 흑돌 (⚫)")
        self.turn_label.setFont(QFont("Malgun Gothic", 13, QFont.Weight.Bold))
        side_layout.addWidget(self.turn_label)

        self.opening_box = QGroupBox("오프닝 렌주 컨트롤")
        op_layout = QVBoxLayout(self.opening_box)
        self.opening_status_lbl = QLabel("주형 정보")
        self.opening_status_lbl.setWordWrap(True)
        self.swap_btn = QPushButton("🔄 흑백 교체 (Swap)")
        self.swap_btn.clicked.connect(self.handle_swap)
        op_layout.addWidget(self.opening_status_lbl)
        op_layout.addWidget(self.swap_btn)
        side_layout.addWidget(self.opening_box)

        eval_group = QGroupBox("실시간 판세 분석 (흑 vs 백)")
        eval_layout = QVBoxLayout(eval_group)
        eval_layout.setSpacing(8)

        wr_text_row = QHBoxLayout()
        self.black_wr_label = QLabel("⚫ 흑 50.0%")
        self.black_wr_label.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        self.black_wr_label.setStyleSheet("color: #b5bac1;")

        self.white_wr_label = QLabel("백 50.0% ⚪")
        self.white_wr_label.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        self.white_wr_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.white_wr_label.setStyleSheet("color: #ffffff;")

        wr_text_row.addWidget(self.black_wr_label)
        wr_text_row.addWidget(self.white_wr_label)
        eval_layout.addLayout(wr_text_row)

        self.winrate_bar = QProgressBar()
        self.winrate_bar.setRange(0, 1000)
        self.winrate_bar.setValue(500)
        self.winrate_bar.setTextVisible(False)
        self.winrate_bar.setStyleSheet("""
            QProgressBar {
                background-color: #f2f3f5;
                border: 1px solid #4e5058;
                border-radius: 5px;
                height: 18px;
            }
            QProgressBar::chunk {
                background-color: #141517;
                border-top-left-radius: 4px;
                border-bottom-left-radius: 4px;
            }
        """)
        eval_layout.addWidget(self.winrate_bar)

        self.analysis_stats_label = QLabel("분석: 대기 중")
        self.analysis_stats_label.setStyleSheet("color: #949ba4; font-size: 12px;")
        eval_layout.addWidget(self.analysis_stats_label)

        self.ai_stats_label = QLabel("AI 착수 연산: 대기 중")
        self.ai_stats_label.setStyleSheet("color: #80848e; font-size: 11px;")
        eval_layout.addWidget(self.ai_stats_label)

        side_layout.addWidget(eval_group)
        side_layout.addStretch()

        restart_btn = QPushButton("새 대국 시작")
        restart_btn.clicked.connect(self.start_game)
        lobby_btn = QPushButton("초기 화면으로 돌아가기")
        lobby_btn.clicked.connect(self.return_to_lobby)

        side_layout.addWidget(restart_btn)
        side_layout.addWidget(lobby_btn)

        main_layout.addWidget(side_panel, stretch=1)
        self.stack.addWidget(game_page)

    def _update_winrate_gauge(self, target_b_wr: float, immediate: bool = False):
        if immediate or target_b_wr in (0.0, 1.0):
            self.displayed_black_wr = target_b_wr
        else:
            self.displayed_black_wr = (self.displayed_black_wr * 0.55) + (target_b_wr * 0.45)

        b_wr = self.displayed_black_wr
        w_wr = 1.0 - b_wr
        self.black_wr_label.setText(f"⚫ 흑 {b_wr*100:.1f}%")
        self.white_wr_label.setText(f"백 {w_wr*100:.1f}% ⚪")
        self.winrate_bar.setValue(int(round(b_wr * 1000)))

    def start_game(self):
        self.stop_all_workers()
        GomokuSearchEngine.KILL_PLAN_CACHE.clear()

        self.game_mode = "pvp" if self.rb_pvp.isChecked() else "pve"
        self.difficulty = self.diff_slider.value()

        if self.rb_free.isChecked():
            self.rule_mode = "freestyle"
        elif self.rb_renju.isChecked():
            self.rule_mode = "renju"
        else:
            self.rule_mode = "opening_renju"

        if self.rb_black.isChecked():
            self.human_color = BLACK
        elif self.rb_white.isChecked():
            self.human_color = WHITE
        else:
            self.human_color = random.choice([BLACK, WHITE])

        self.board.rule_mode = self.rule_mode
        self.board.reset()
        self._update_winrate_gauge(0.5, immediate=True)
        self.board_widget.clear_ai_eval_moves()

        rule_kor = {"freestyle": "프리룰", "renju": "정통 렌주룰", "opening_renju": "오프닝 렌주"}[self.rule_mode]
        if self.game_mode == "pvp":
            mode_kor = "사람 vs 사람"
        else:
            my_col_kor = "흑돌" if self.human_color == BLACK else "백돌"
            mode_kor = f"사람({my_col_kor}) vs AI (Lv.{self.difficulty})"
        self.info_header.setText(f"{mode_kor}\n규칙: {rule_kor}")

        self.update_ui_state()
        self.stack.setCurrentIndex(1)

        self.sync_turn_workers()

    def return_to_lobby(self):
        self.stop_all_workers()
        self.stack.setCurrentIndex(0)

    def stop_ai_worker(self):
        if self.ai_worker is not None:
            self.ai_worker.stop()
            self.ai_worker.wait(0.2)
            self.ai_worker = None

    def stop_analysis_worker(self):
        if self.analysis_worker is not None:
            self.analysis_worker.stop()
            self.analysis_worker.wait(0.2)
            self.analysis_worker = None

    def stop_all_workers(self):
        self.poll_timer.stop()
        self.stop_ai_worker()
        self.stop_analysis_worker()

    def restart_analysis_worker(self):
        """플레이어 차례(또는 경기 종료 시)에만 백그라운드 분석 워커 가동"""
        self.stop_analysis_worker()
        self.analysis_worker = AnalysisWorker(self.board)
        self.analysis_worker.start()
        if not self.poll_timer.isActive():
            self.poll_timer.start()

    def sync_turn_workers(self):
        """
        현재 턴 주인에 따라 워커 배분:
        - AI 차례: AnalysisWorker를 정지시켜 CPU를 AIWorker에 100% 몰아줌
        - 플레이어 차례 (또는 2인용): AnalysisWorker만 단독 가동하여 실시간 판세 분석
        """
        if self.board.game_over:
            self.stop_ai_worker()
            self.restart_analysis_worker()
            return

        if self.game_mode == "pve" and self.board.current_turn != self.human_color:
            # AI 차례 -> 분석기 중단 후 AI 연산 전념
            self.stop_analysis_worker()
            self.analysis_stats_label.setText("분석: AI 수읽기 연동 중...")
            self.check_ai_turn()
        else:
            # 플레이어 차례 -> 분석기 단독 가동
            self.stop_ai_worker()
            self.restart_analysis_worker()

    def handle_swap(self):
        if self.board.opening_state in ("SWAP1", "SWAP2"):
            if self.game_mode == "pve":
                self.human_color = WHITE if self.human_color == BLACK else BLACK
            if self.board.opening_state == "SWAP1":
                self.board.opening_state = "MOVE4"
            elif self.board.opening_state == "SWAP2":
                self.board.opening_state = "OFFER5"
            self.board.refresh_forbidden_points()
            self.update_ui_state()
            self.sync_turn_workers()

    def on_board_clicked(self, r: int, c: int):
        if self.board.game_over:
            return
        if self.game_mode == "pve" and self.board.current_turn != self.human_color:
            return

        if self.board.place_stone(r, c):
            self.board_widget.clear_ai_eval_moves()
            self.update_ui_state()
            self.sync_turn_workers()

    def check_ai_turn(self):
        if self.game_mode != "pve" or self.board.game_over:
            return
        if self.board.current_turn != self.human_color:
            if self.board.opening_state == "OFFER5":
                cands = []
                for r in range(BOARD_SIZE):
                    for c in range(BOARD_SIZE):
                        ok, _ = self.board.is_valid_move(r, c, BLACK)
                        if ok:
                            cands.append((r, c))
                for r, c in random.sample(cands, 2):
                    self.board.place_stone(r, c)
                self.update_ui_state()
                self.sync_turn_workers()
                return
            elif self.board.opening_state == "CHOOSE5":
                choice = random.choice(self.board.offer5_candidates)
                self.board.place_stone(*choice)
                self.update_ui_state()
                self.sync_turn_workers()
                return

            self.stop_ai_worker()
            self.stop_analysis_worker()
            self.ai_worker = AIWorker(self.board, self.difficulty, self.board.current_turn)
            self.ai_worker.start()
            if not self.poll_timer.isActive():
                self.poll_timer.start()

    def poll_workers(self):
        # 1. 플레이어 차례일 때 돌아가는 실시간 중립 판세 분석기 결과 반영
        if self.analysis_worker is not None:
            with self.analysis_worker._lock:
                ana = self.analysis_worker.latest_analysis
                self.analysis_worker.latest_analysis = None
            if ana is not None:
                target_b_wr, depth, nodes, nps = ana
                self._update_winrate_gauge(target_b_wr, immediate=(depth == 0))
                if depth == 0:
                    self.analysis_stats_label.setText("분석: 초기 형세 평가")
                else:
                    self.analysis_stats_label.setText(f"분석: Depth {depth} | {nodes:,} nodes ({nps:,}/s)")

        # 2. AI 차례일 때 단독 가동되는 AIWorker 진행 상태 및 착수 완료 반영
        if self.ai_worker is not None:
            with self.ai_worker._lock:
                prog = self.ai_worker.latest_progress
                self.ai_worker.latest_progress = None
                done = self.ai_worker.is_finished
                move = self.ai_worker.final_move

            if prog is not None:
                eval_moves, depth, nodes, nps, ai_b_wr = prog
                self.board_widget.set_ai_eval_moves(eval_moves)
                self._update_winrate_gauge(ai_b_wr, immediate=(depth == 0))
                if depth == 0:
                    self.ai_stats_label.setText("AI 착수 연산: 필승 킬각 포착! 즉시 착수")
                else:
                    self.ai_stats_label.setText(f"AI 착수 연산: Depth {depth} | {nodes:,} nodes ({nps:,}/s)")

            if done:
                self.ai_worker = None
                self.ai_stats_label.setText("AI 착수 연산: 완료")
                if move is not None:
                    self.on_ai_move_ready(move[0], move[1])

    def on_ai_move_ready(self, r: int, c: int):
        self.board_widget.clear_ai_eval_moves()
        self.board.place_stone(r, c)
        self.update_ui_state()
        self.sync_turn_workers()

    def update_ui_state(self):
        if self.game_mode == "pve":
            self.board_widget.set_human_interact(self.board.current_turn == self.human_color)
        else:
            self.board_widget.set_human_interact(True)

        self.board_widget.update()

        if self.rule_mode == "opening_renju" and self.board.opening_state != "PLAYING":
            self.opening_box.setVisible(True)
            st = self.board.opening_state
            msg_map = {
                "SWAP1": f"주형: {self.board.opening_name}\n백(4수)은 스왑하거나 4수를 두세요.",
                "MOVE4": "스왑 완료! 이제 4수를 착수하세요.",
                "SWAP2": "4수 착수 완료! 흑은 스왑하거나 5수 후보 2개를 제시하세요.",
                "OFFER5": f"5수 후보 2곳을 클릭하세요 ({len(self.board.offer5_candidates)}/2)",
                "CHOOSE5": "백이 붉은 후보 2개 중 최종 5수를 클릭해 선택하세요."
            }
            self.opening_status_lbl.setText(msg_map.get(st, ""))
            self.swap_btn.setVisible(st in ("SWAP1", "SWAP2"))
        else:
            self.opening_box.setVisible(False)

        if self.board.game_over:
            if self.board.winner == BLACK:
                res = "흑돌 (⚫) 승리!"
            elif self.board.winner == WHITE:
                res = "백돌 (⚪) 승리!"
            else:
                res = "무승부!"
            self.turn_label.setText(f"경기 종료: {res}")
            QMessageBox.information(self, "대국 종료", res)
        else:
            turn_str = "흑돌 (⚫)" if self.board.current_turn == BLACK else "백돌 (⚪)"
            if self.game_mode == "pve":
                who = "내 차례" if self.board.current_turn == self.human_color else "AI 연산 중..."
                self.turn_label.setText(f"차례: {turn_str} - {who}")
            else:
                self.turn_label.setText(f"현재 차례: {turn_str}")

    def closeEvent(self, event):
        self.stop_all_workers()
        event.accept()