import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame
from PySide6.QtGui import QPainter, QPen, QColor, QTabletEvent, QFont
from PySide6.QtCore import Qt, QPointF


class GuitarCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(600, 400)

        # Match your working hardware test setting exactly
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, False)

        self.string_names = ['E', 'A', 'D', 'G', 'B', 'e']
        self.num_strings = 6
        self.string_y_positions = []
        self.last_pen_pos = None

    def resizeEvent(self, event):
        """Recalculate coordinates for string spacing when window resizes."""
        super().resizeEvent(event)
        self.string_y_positions.clear()
        height = self.height()
        padding = 50
        usable_height = height - (padding * 2)
        spacing = usable_height / (self.num_strings - 1)
        for i in range(self.num_strings):
            y = padding + (i * spacing)
            self.string_y_positions.append(y)

    def paintEvent(self, event):
        """Draw a professional modern guitar canvas."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Dark modern slate background
        painter.fillRect(self.rect(), QColor("#18191e"))

        # Draw elegant glowing guitar strings
        for i, y in enumerate(self.string_y_positions):
            thickness = max(1, 5 - i)
            # Make low strings look thicker and distinct
            painter.setPen(QPen(QColor("#a2a5b3"), thickness))
            painter.drawLine(0, int(y), self.width(), int(y))

            # String Labels
            painter.setPen(QColor("#5c5e69"))
            painter.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
            painter.drawText(15, int(y) - 6, self.string_names[i])

    def check_strum_intersection(self, p1, p2, pressure):
        """Calculate vector crossover between pen tracking frames."""
        y_min = min(p1.y(), p2.y())
        y_max = max(p1.y(), p2.y())

        for i, string_y in enumerate(self.string_y_positions):
            if y_min <= string_y <= y_max:
                direction = "DOWN ⬇" if p2.y() > p1.y() else "UP ⬆"
                # Push the data safely back up to the window's sidebar logger
                self.window().log_pluck(i, self.string_names[i], direction, pressure)

    def tabletEvent(self, event: QTabletEvent):
        """Stable PySide6 input hook matching your working prototype perfectly."""
        current_pos = event.position()
        pressure = event.pressure()  # Native float [0.0 - 1.0]

        if event.type() == QTabletEvent.Type.TabletMove:
            if self.last_pen_pos:
                self.check_strum_intersection(self.last_pen_pos, current_pos, pressure)
            self.last_pen_pos = current_pos

        elif event.type() == QTabletEvent.Type.TabletRelease:
            self.last_pen_pos = None

        event.accept()  # Prevent event re-routing or leaking to system mouse loops


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Acoustic Scribe — Production Build [PySide6]")
        self.setGeometry(100, 100, 950, 550)
        self.setStyleSheet("background-color: #0c0e12;")

        # Core Layout Setup
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Gorgeous DAWs Styled Left Sidebar
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(260)
        self.sidebar.setStyleSheet("background-color: #0f1015; border-right: 1px solid #232630;")
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(20, 30, 20, 30)

        self.title_lbl = QLabel("ACOUSTIC SCRIBE")
        self.title_lbl.setStyleSheet(
            "font-family: 'Arial'; font-size: 16px; font-weight: bold; color: #7856ff; letter-spacing: 1px;")
        sidebar_layout.addWidget(self.title_lbl)

        sidebar_layout.addStretch()

        # Interactive Monitor Log
        self.console_lbl = QLabel("Strum Monitor:\n\n[Touch pen to canvas\nto strike strings]")
        self.console_lbl.setWordWrap(True)
        self.console_lbl.setStyleSheet("font-family: 'Consolas'; font-size: 11px; color: #6e738c; line-height: 150%;")
        sidebar_layout.addWidget(self.console_lbl)

        sidebar_layout.addStretch()
        layout.addWidget(self.sidebar)

        # 2. Performance Tracking Canvas
        self.canvas = GuitarCanvas(self)
        layout.addWidget(self.canvas)

    def log_pluck(self, string_idx, string_name, direction, pressure):
        pressure_pct = int(pressure * 100)

        # Dynamic warning color depending on how heavy you hit the string
        color = "#40c4ff" if pressure_pct < 40 else "#7856ff" if pressure_pct < 75 else "#ff4878"

        log_text = (f"<span style='color: #dcdcd3; font-weight: bold;'>🎸 STRING PLUCKED!</span><br><br>"
                    f"String    : <span style='color: #4ba3e3;'>{string_idx} ({string_name})</span><br>"
                    f"Direction : <span style='color: #eedd82;'>{direction}</span><br>"
                    f"Pressure  : <span style='color: {color}; font-weight: bold;'>{pressure_pct}%</span>")
        self.console_lbl.setText(log_text)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())