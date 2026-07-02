from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QMouseEvent
from PySide6.QtCore import Qt, Signal


class VisualFretboard(QWidget):
    chord_changed = Signal(list)  # Emits new array layout like [0, 3, 2, 0, 1, 0]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 160)
        self.setFixedHeight(180)

        self.num_strings = 6
        self.num_frets = 5  # Displaying first 5 frets for comfortable composition

        # State: 0 = open, -1 = muted/blocked, >0 = pressed fret number
        self.current_array = [0, 0, 0, 0, 0, 0]
        self.string_labels = ['E', 'A', 'D', 'G', 'B', 'e']

    def load_array(self, array):
        """Loads an array into the interactive grid view."""
        self.current_array = list(array)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#111216"))

        w, h = self.width(), self.height()
        pad_x, pad_y = 50, 25
        grid_w, grid_h = w - (pad_x * 2), h - (pad_y * 2)

        fret_w = grid_w / self.num_frets
        string_h = grid_h / (self.num_strings - 1)

        # Draw Nut & Fret wires
        painter.setPen(QPen(QColor("#7856ff"), 4))  # Nut
        painter.drawLine(pad_x, pad_y, pad_x, h - pad_y)

        painter.setPen(QPen(QColor("#3d4154"), 2))
        for f in range(1, self.num_frets + 1):
            x = pad_x + (f * fret_w)
            painter.drawLine(int(x), pad_y, int(x), h - pad_y)

        # Draw Horizontal Strings
        for s in range(self.num_strings):
            y = pad_y + (s * string_h)
            painter.setPen(QPen(QColor("#5c5e69"), max(1, 4 - s)))
            painter.drawLine(pad_x, int(y), w - pad_x, int(y))

            # Label indicators
            state = self.current_array[s]
            lbl = "X" if state == -1 else "0" if state == 0 else str(state)
            color = "#ff4878" if state == -1 else "#40c4ff" if state == 0 else "#7856ff"

            painter.setPen(QColor(color))
            painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            painter.drawText(20, int(y) + 4, f"{self.string_labels[s]}:{lbl}")

            # Draw Pressed Note Markers
            if state > 0:
                cx = pad_x + ((state - 0.5) * fret_w)
                painter.setBrush(QColor("#7856ff"))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(int(cx) - 8, int(y) - 8, 16, 16)

    def mousePressEvent(self, event: QMouseEvent):
        w, h = self.width(), self.height()
        pad_x, pad_y = 50, 25
        grid_w, grid_h = w - (pad_x * 2), h - (pad_y * 2)

        fret_w = grid_w / self.num_frets
        string_h = grid_h / (self.num_strings - 1)

        # Determine closest string clicked
        s_idx = round((event.y() - pad_y) / string_h)
        s_idx = max(0, min(self.num_strings - 1, s_idx))

        # Determine click interaction type
        if event.x() < pad_x:  # Mute Toggle Zone
            self.current_array[s_idx] = -1 if self.current_array[s_idx] != -1 else 0
        else:  # Fret targeting grid selection
            f_idx = int((event.x() - pad_x) / fret_w) + 1
            if f_idx <= self.num_frets:
                self.current_array[s_idx] = 0 if self.current_array[s_idx] == f_idx else f_idx

        self.update()
        self.chord_changed.emit(self.current_array)