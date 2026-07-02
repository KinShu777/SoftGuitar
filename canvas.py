from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QPen, QColor, QTabletEvent, QFont
from PySide6.QtCore import Qt, Signal


class GuitarCanvas(QWidget):
    string_plucked = Signal(int, str, str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(600, 400)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, False)

        self.string_names = ['E', 'A', 'D', 'G', 'B', 'e']
        self.num_strings = 6
        self.string_y_positions = []
        self.last_pen_pos = None

        # Default spacing height matching our previous comfortable layout
        self.strum_zone_height = 140

    def update_spacing(self, new_height):
        """Public method to change string spacing dynamically from the UI slider."""
        self.strum_zone_height = new_height
        self.recalculate_string_positions()
        self.update()  # Force repaint instantly

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.recalculate_string_positions()

    def recalculate_string_positions(self):
        """Calculates where strings go based on the current strum zone height attribute."""
        self.string_y_positions.clear()
        height = self.height()

        start_y = (height - self.strum_zone_height) / 2
        spacing = self.strum_zone_height / (self.num_strings - 1)

        for i in range(self.num_strings):
            y = start_y + (i * spacing)
            self.string_y_positions.append(y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#18191e"))

        if self.string_y_positions:
            zone_top = int(self.string_y_positions[0] - 20)
            zone_bottom = int(self.string_y_positions[-1] + 20)
            painter.fillRect(0, zone_top, self.width(), zone_bottom - zone_top, QColor("#1c1d24"))

        for i, y in enumerate(self.string_y_positions):
            thickness = max(1, 5 - i)
            painter.setPen(QPen(QColor("#a2a5b3"), thickness))
            painter.drawLine(0, int(y), self.width(), int(y))

            painter.setPen(QColor("#5c5e69"))
            painter.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
            painter.drawText(15, int(y) - 6, self.string_names[i])

    def check_strum_intersection(self, p1, p2, pressure):
        y_min = min(p1.y(), p2.y())
        y_max = max(p1.y(), p2.y())

        for i, string_y in enumerate(self.string_y_positions):
            if y_min <= string_y <= y_max:
                direction = "DOWN ⬇" if p2.y() > p1.y() else "UP ⬆"
                self.string_plucked.emit(i, self.string_names[i], direction, pressure)

    def tabletEvent(self, event: QTabletEvent):
        current_pos = event.position()
        pressure = event.pressure()

        if event.type() == QTabletEvent.Type.TabletMove:
            if self.last_pen_pos:
                self.check_strum_intersection(self.last_pen_pos, current_pos, pressure)
            self.last_pen_pos = current_pos

        elif event.type() == QTabletEvent.Type.TabletRelease:
            self.last_pen_pos = None

        event.accept()