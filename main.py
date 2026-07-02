import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                               QVBoxLayout, QLabel, QFrame, QSlider, QSpinBox)
from PySide6.QtCore import Qt
from canvas import GuitarCanvas
from guitar_audio import AudioEngine  # Corrected filename import


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Acoustic Scribe — Studio Workspace")
        self.setGeometry(100, 100, 1100, 650)
        self.setStyleSheet("background-color: #0c0e12;")

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.audio = AudioEngine()
        self.audio.start()

        # Hardcoded reference constants matching your open string frequencies
        self.open_strings = [82.41, 110.00, 146.83, 196.00, 246.94, 329.63]

        # Base Layout Shell
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # --- LEFT SIDEBAR ---
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(280)
        self.sidebar.setStyleSheet("background-color: #0f1015; border-right: 1px solid #232630;")
        sb_layout = QVBoxLayout(self.sidebar)
        sb_layout.setContentsMargins(15, 20, 15, 20)

        # Capo Control (Restored full keyboard/arrow key focus mechanics)
        self.capo_lbl = QLabel("Capo Position (Fret)")
        self.capo_lbl.setStyleSheet("color: #a2a5b3; font-family: 'Arial'; font-weight: bold; font-size: 11px;")
        sb_layout.addWidget(self.capo_lbl)

        self.capo_box = QSpinBox()
        self.capo_box.setRange(0, 12)  # Max capo positioning limit
        self.capo_box.setValue(0)
        self.capo_box.setSuffix(" Fret")
        # Removed NoFocus so you can click, type numbers, or use up/down keyboard arrows seamlessly
        self.capo_box.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.capo_box.valueChanged.connect(self.handle_capo_pitch_shift)
        sb_layout.addWidget(self.capo_box)

        sb_layout.addSpacing(20)

        # Ergonomic Spacing Slider (Untouched)
        self.spacing_lbl = QLabel("Strum Area Bounds")
        self.spacing_lbl.setStyleSheet("color: #a2a5b3; font-family: 'Arial'; font-weight: bold; font-size: 11px;")
        sb_layout.addWidget(self.spacing_lbl)

        self.spacing_slider = QSlider(Qt.Orientation.Horizontal)
        self.spacing_slider.setRange(50, 250)
        self.spacing_slider.setValue(140)
        self.spacing_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.spacing_slider.valueChanged.connect(lambda v: self.canvas.update_spacing(v))
        sb_layout.addWidget(self.spacing_slider)

        sb_layout.addStretch()
        layout.addWidget(self.sidebar)

        # --- CENTER/RIGHT SUITE ---
        center_suite = QWidget()
        suite_layout = QVBoxLayout(center_suite)
        suite_layout.setContentsMargins(15, 15, 15, 15)

        self.canvas = GuitarCanvas()
        self.canvas.string_plucked.connect(lambda idx, n, d, p: self.audio.trigger_pluck(idx, p))

        self.perf_lbl = QLabel("PERFORMANCE STRUM INSTRUMENT STRINGS")
        self.perf_lbl.setStyleSheet(
            "color: #a2a5b3; font-family: 'Arial'; font-weight: bold; font-size: 11px; letter-spacing: 0.5px;")

        suite_layout.addWidget(self.perf_lbl)
        suite_layout.addWidget(self.canvas)

        layout.addWidget(center_suite)

    def handle_capo_pitch_shift(self, fret_value):
        """Calculates equal-temperament pitch scaling and shifts the audio engine's string array directly."""
        for i in range(6):
            # Frequency transposition formula: f = f0 * 2^(fret / 12)
            self.audio.current_frequencies[i] = self.open_strings[i] * (2.0 ** (fret_value / 12.0))

    def closeEvent(self, event):
        self.audio.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())