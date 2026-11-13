from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QLinearGradient
from core.board import GomokuBoard
from core.rules import BOARD_SIZE, EMPTY, BLACK


class BoardWidget(QWidget):
    cell_clicked = pyqtSignal(int, int)

    def __init__(self, board: GomokuBoard):
        super().__init__()
        self.board = board
        self.setMinimumSize(620, 620)
        self.setMouseTracking(True)
        self.hover_pos = None
        self.ai_eval_moves = []
        self.can_human_interact = True  # 사람 차례일 때만 호버 돌 표시

        # Windows DirectWrite 크래시 방지를 위해 기본 시스템 폰트를 1회만 생성해 재사용
        self.font_coord = QFont("Malgun Gothic", 9, QFont.Weight.Bold)
        self.font_stone = QFont("Malgun Gothic", 9, QFont.Weight.Bold)
        self.font_eval = QFont("Malgun Gothic", 8, QFont.Weight.Bold)

    def set_human_interact(self, enabled: bool):
        self.can_human_interact = enabled
        self.update()

    def set_ai_eval_moves(self, moves: list):
        self.ai_eval_moves = moves
        self.update()

    def clear_ai_eval_moves(self):
        self.ai_eval_moves = []
        self.update()

    def get_board_metrics(self):
        size = min(self.width(), self.height()) - 40
        cell_size = size / (BOARD_SIZE - 1)
        offset_x = (self.width() - size) / 2
        offset_y = (self.height() - size) / 2
        return offset_x, offset_y, cell_size, size

    def mouseMoveEvent(self, event):
        ox, oy, cs, _ = self.get_board_metrics()
        c = round((event.position().x() - ox) / cs)
        r = round((event.position().y() - oy) / cs)
        if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
            self.hover_pos = (r, c)
        else:
            self.hover_pos = None
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.hover_pos:
            self.cell_clicked.emit(*self.hover_pos)

    def winrate_to_color(self, wr: float) -> QColor:
        wr = max(0.0, min(1.0, wr))
        if wr < 0.5:
            ratio = wr * 2.0
            r = 235
            g = int(60 + 175 * ratio)
            b = 60
        else:
            ratio = (wr - 0.5) * 2.0
            r = int(235 * (1.0 - ratio) + 40 * ratio)
            g = int(235 * (1.0 - ratio) + 215 * ratio)
            b = int(60 * (1.0 - ratio) + 95 * ratio)
        return QColor(r, g, b, 225)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        ox, oy, cs, board_px = self.get_board_metrics()

        # 1. 오목판 배경
        board_rect = QRectF(ox - 20, oy - 20, board_px + 40, board_px + 40)
        painter.setBrush(QBrush(QColor(218, 178, 115)))
        painter.setPen(QPen(QColor(130, 95, 50), 2))
        painter.drawRoundedRect(board_rect, 8, 8)

        # 2. 격자선 및 좌표 라벨
        painter.setPen(QPen(QColor(55, 40, 25), 1.2))
        for i in range(BOARD_SIZE):
            pos = i * cs
            painter.drawLine(QPointF(ox, oy + pos), QPointF(ox + board_px, oy + pos))
            painter.drawLine(QPointF(ox + pos, oy), QPointF(ox + pos, oy + board_px))

        painter.setFont(QFont("Pretendard", 9, QFont.Weight.Bold))
        painter.setPen(QColor(70, 50, 30))
        for i in range(BOARD_SIZE):
            col_char = chr(ord('A') + i)
            painter.drawText(QRectF(ox + i * cs - 10, oy - 20, 20, 15), Qt.AlignmentFlag.AlignCenter, col_char)
            painter.drawText(QRectF(ox - 22, oy + i * cs - 10, 18, 20), Qt.AlignmentFlag.AlignCenter, str(15 - i))

        # 화점
        star_points = [(3, 3), (3, 11), (7, 7), (11, 3), (11, 11)]
        painter.setBrush(QBrush(QColor(40, 30, 20)))
        for sr, sc in star_points:
            painter.drawEllipse(QPointF(ox + sc * cs, oy + sr * cs), 4, 4)

        # 3. 착수된 돌 그리기
        stone_radius = cs * 0.44
        for idx, (r, c, col) in enumerate(self.board.history):
            cx, cy = ox + c * cs, oy + r * cs
            grad = QLinearGradient(cx - stone_radius, cy - stone_radius, cx + stone_radius, cy + stone_radius)
            if col == BLACK:
                grad.setColorAt(0, QColor(70, 70, 75))
                grad.setColorAt(1, QColor(15, 15, 18))
            else:
                grad.setColorAt(0, QColor(255, 255, 255))
                grad.setColorAt(1, QColor(205, 205, 210))

            painter.setBrush(QBrush(grad))
            painter.setPen(QPen(QColor(30, 30, 30), 1))
            painter.drawEllipse(QPointF(cx, cy), stone_radius, stone_radius)

            painter.setPen(QColor(230, 230, 230) if col == BLACK else QColor(30, 30, 30))
            painter.setFont(QFont("Pretendard", 9, QFont.Weight.Bold))
            painter.drawText(
                QRectF(cx - stone_radius, cy - stone_radius, stone_radius * 2, stone_radius * 2),
                Qt.AlignmentFlag.AlignCenter, str(idx + 1)
            )

            if idx == len(self.board.history) - 1:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(255, 70, 70), 2.2))
                painter.drawEllipse(QPointF(cx, cy), stone_radius * 0.45, stone_radius * 0.45)

        # 4. 금수 자리 상시 표기
        if not self.board.game_over and self.board.forbidden_points:
            painter.setPen(QPen(QColor(220, 30, 30), 2.4))
            d = cs * 0.24
            for fr, fc in self.board.forbidden_points:
                cx, cy = ox + fc * cs, oy + fr * cs
                painter.drawLine(QPointF(cx - d, cy - d), QPointF(cx + d, cy + d))
                painter.drawLine(QPointF(cx + d, cy - d), QPointF(cx - d, cy + d))

        # 5. 오프닝 렌주 5수 후보 마커
        for cand_idx, (cr, cc) in enumerate(self.board.offer5_candidates):
            cx, cy = ox + cc * cs, oy + cr * cs
            painter.setBrush(QBrush(QColor(230, 60, 60, 170)))
            painter.setPen(QPen(QColor(255, 255, 255), 1.5))
            painter.drawEllipse(QPointF(cx, cy), stone_radius * 0.75, stone_radius * 0.75)
            painter.setFont(QFont("Pretendard", 9, QFont.Weight.Bold))
            painter.drawText(
                QRectF(cx - 15, cy - 15, 30, 30),
                Qt.AlignmentFlag.AlignCenter, f"후보{cand_idx+1}"
            )

        # 6. AI 실시간 탐색 승률 원형 히트맵 오버레이
        if self.ai_eval_moves:
            sorted_eval = sorted(self.ai_eval_moves, key=lambda x: x[2], reverse=True)
            for rank, (r, c, wr) in enumerate(sorted_eval):
                if self.board.grid[r, c] != EMPTY:
                    continue
                cx, cy = ox + c * cs, oy + r * cs
                color = self.winrate_to_color(wr)
                circle_r = cs * 0.41

                if rank == 0:
                    painter.setPen(QPen(QColor(255, 255, 255), 2.5))
                else:
                    painter.setPen(QPen(QColor(20, 20, 20, 160), 1.2))

                painter.setBrush(QBrush(color))
                painter.drawEllipse(QPointF(cx, cy), circle_r, circle_r)

                painter.setPen(QColor(15, 15, 15) if wr > 0.35 else QColor(255, 255, 255))
                painter.setFont(QFont("Pretendard", 8, QFont.Weight.Bold))
                painter.drawText(
                    QRectF(cx - circle_r, cy - circle_r, circle_r * 2, circle_r * 2),
                    Qt.AlignmentFlag.AlignCenter, f"{int(round(wr * 100))}%"
                )

        # 7. 마우스 호버 가이드 (사람이 둘 수 있는 차례일 때만 표시, AI 차례일 땐 숨김)
        if self.can_human_interact and self.hover_pos and not self.board.game_over:
            hr, hc = self.hover_pos
            if self.board.grid[hr, hc] == EMPTY and (hr, hc) not in self.board.forbidden_points:
                cx, cy = ox + hc * cs, oy + hr * cs
                preview_col = QColor(0, 0, 0, 80) if self.board.current_turn == BLACK else QColor(255, 255, 255, 110)
                painter.setBrush(QBrush(preview_col))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(cx, cy), stone_radius * 0.85, stone_radius * 0.85)