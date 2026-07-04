import sys
import os
import json
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                               QVBoxLayout, QLabel, QFrame, QSlider, QSpinBox,
                               QPushButton, QTreeWidget, QTreeWidgetItem)
from PySide6.QtCore import Qt
from canvas import GuitarCanvas
from guitar_audio import AudioEngine
from preset_editor import PresetEditor

PRESET_STORAGE_FILE = "guitar_presets.json"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Acoustic Scribe — Studio Workspace")
        self.setGeometry(100, 100, 1150, 680)
        self.setStyleSheet("background-color: #0c0e12; color: #fff;")

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.audio = AudioEngine()
        self.audio.start()

        # TEST HOOK: Load a warm C Major shape and clamp a Capo on the 2nd Fret
        self.audio.set_capo(2)
        self.audio.set_chord("C Major")

        self.open_strings = [82.41, 110.00, 146.83, 196.00, 246.94, 329.63]
        self.loaded_presets = {}
        self.active_preset_name = None
        self.active_chord_map = {}

        # Main Structural Shell Layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- LEFT SIDEBAR PANEL ---
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(290)
        self.sidebar.setStyleSheet("background-color: #0f1015; border-right: 1px solid #232630;")
        sb_layout = QVBoxLayout(self.sidebar)
        sb_layout.setContentsMargins(15, 20, 15, 20)

        self.title_lbl = QLabel("ACOUSTIC SCRIBE")
        self.title_lbl.setStyleSheet(
            "font-family: 'Arial'; font-size: 15px; font-weight: bold; color: #7856ff; letter-spacing: 1px;")
        sb_layout.addWidget(self.title_lbl)

        sb_layout.addSpacing(20)

        # Tree hierarchy containing dropdown preset selectors
        sb_layout.addWidget(QLabel("PRESETS"))
        self.preset_tree = QTreeWidget()
        self.preset_tree.setHeaderHidden(True)
        self.preset_tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.preset_tree.setStyleSheet("""
            QTreeWidget {
                background-color: #13151c;
                border: 1px solid #222531;
                color: #e2e4ed;
                font-family: 'Arial';
            }
            QTreeWidget::item { padding: 5px; }
            QTreeWidget::item:selected { background-color: #242836; color: #7856ff; font-weight: bold; }
        """)
        self.preset_tree.itemClicked.connect(self.handle_preset_selection)
        sb_layout.addWidget(self.preset_tree)

        # Interactive Control Buttons
        btn_layout = QHBoxLayout()
        self.new_preset_btn = QPushButton("Create New +")
        self.new_preset_btn.setStyleSheet(
            "background-color: #222531; border: 1px solid #33384a; padding: 6px; font-weight: bold;")
        self.new_preset_btn.clicked.connect(self.open_new_preset_wizard)
        btn_layout.addWidget(self.new_preset_btn)

        self.edit_preset_btn = QPushButton("Edit ✏️")
        self.edit_preset_btn.setStyleSheet("background-color: #222531; border: 1px solid #33384a; padding: 6px;")
        self.edit_preset_btn.clicked.connect(self.edit_selected_preset)
        btn_layout.addWidget(self.edit_preset_btn)
        sb_layout.addLayout(btn_layout)

        sb_layout.addSpacing(20)

        # Capo Control
        self.capo_lbl = QLabel("Capo Position (Fret)")
        self.capo_lbl.setStyleSheet("color: #a2a5b3; font-family: 'Arial'; font-weight: bold; font-size: 11px;")
        sb_layout.addWidget(self.capo_lbl)

        self.capo_box = QSpinBox()
        self.capo_box.setRange(0, 12)
        self.capo_box.setValue(0)
        self.capo_box.setSuffix(" Fret")
        self.capo_box.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.capo_box.valueChanged.connect(self.handle_capo_pitch_shift)
        sb_layout.addWidget(self.capo_box)

        sb_layout.addSpacing(20)
        self.pm_lbl = QLabel("Palm Mute Intensity")
        self.pm_lbl.setStyleSheet("color: #a2a5b3; font-family: 'Arial'; font-weight: bold; font-size: 11px;")
        sb_layout.addWidget(self.pm_lbl)

        self.pm_slider = QSlider(Qt.Orientation.Horizontal)
        self.pm_slider.setRange(0, 100)
        self.pm_slider.setValue(0)
        self.pm_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.pm_slider.valueChanged.connect(self.handle_palm_mute_slider_change)
        sb_layout.addWidget(self.pm_slider)

        sb_layout.addSpacing(20)

        # Spacing Bound Sliders
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

        # --- CENTER PERFORMANCE SUITE ---
        center_suite = QWidget()
        suite_layout = QVBoxLayout(center_suite)
        suite_layout.setContentsMargins(20, 20, 20, 20)

        self.perf_lbl = QLabel("PERFORMANCE STRUM INSTRUMENT STRINGS")
        self.perf_lbl.setStyleSheet(
            "color: #a2a5b3; font-family: 'Arial'; font-weight: bold; font-size: 11px; letter-spacing: 0.5px;")
        suite_layout.addWidget(self.perf_lbl)

        self.active_status_lbl = QLabel("No Chord Active (Open Strings Playing)")
        self.active_status_lbl.setStyleSheet(
            "color: #eedd82; font-family: 'Arial'; font-size: 13px; font-weight: bold; margin-bottom: 5px;")
        suite_layout.addWidget(self.active_status_lbl)

        self.canvas = GuitarCanvas()
        self.canvas.string_plucked.connect(lambda idx, n, d, p: self.audio.trigger_pluck(idx, p))
        suite_layout.addWidget(self.canvas)

        layout.addWidget(center_suite, stretch=4)

        # Load any existing data from disk file storage framework
        self.load_presets_from_file()

    def handle_capo_pitch_shift(self, fret_value):
        for i in range(6):
            self.audio.open_frequencies[i] = self.open_strings[i] * (2.0 ** (fret_value / 12.0))
        # Recalculate immediate playback arrays inside callback
        self.audio.set_chord([0, 0, 0, 0, 0, 0])

    def handle_palm_mute_slider_change(self, value):
        self.audio.set_palm_mute(value / 100.0)

    def open_new_preset_wizard(self):
        editor = PresetEditor(self)
        editor.preset_saved.connect(self.save_preset_payload)
        editor.exec()

    def edit_selected_preset(self):
        item = self.preset_tree.currentItem()
        if not item: return
        # Get the master top root item
        root_item = item if not item.parent() else item.parent()
        p_name = root_item.text(0)

        editor = PresetEditor(self, preset_name=p_name, preset_data=self.loaded_presets.get(p_name))
        editor.preset_saved.connect(self.save_preset_payload)
        editor.exec()

    def save_preset_payload(self, name, chord_data):
        self.loaded_presets[name] = chord_data
        self.sync_presets_to_storage_file()
        self.rebuild_preset_tree_ui()

    def sync_presets_to_storage_file(self):
        with open(PRESET_STORAGE_FILE, "w") as f:
            json.dump(self.loaded_presets, f, indent=4)

    def load_presets_from_file(self):
        if os.path.exists(PRESET_STORAGE_FILE):
            try:
                with open(PRESET_STORAGE_FILE, "r") as f:
                    self.loaded_presets = json.load(f)
            except Exception:
                self.loaded_presets = {}
        self.rebuild_preset_tree_ui()

    def rebuild_preset_tree_ui(self):
        self.preset_tree.clear()
        for p_name, chords in self.loaded_presets.items():
            root = QTreeWidgetItem([p_name])
            for kb, info in chords.items():
                child = QTreeWidgetItem([f"Key [{kb}] ➔ {info['name']}"])
                root.addChild(child)
            self.preset_tree.addTopLevelItem(root)

    def handle_preset_selection(self, item, column):
        root_item = item if not item.parent() else item.parent()
        self.active_preset_name = root_item.text(0)
        self.active_chord_map = self.loaded_presets.get(self.active_preset_name, {})
        self.active_status_lbl.setText(
            f"Preset Active: {self.active_preset_name} (Press assigned keys to shift chords!)")
        self.setFocus()  # Re-focus window so keyboard captures hit cleanly

    def keyPressEvent(self, event):
        """Monitors global engine scope to shift target chord frequencies cleanly."""
        key_text = event.text()
        if self.active_chord_map and key_text in self.active_chord_map:
            chord_info = self.active_chord_map[key_text]
            # Feed positions directly into the audio oscillator loops
            self.audio.set_chord(chord_info["frets"])
            self.active_status_lbl.setText(
                f"Active Chord: {chord_info['name']} {chord_info['frets']} (Preset: {self.active_preset_name})")
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.audio.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())