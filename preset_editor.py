from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QLineEdit, QSlider, QListWidget, QFrame, QMessageBox)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush


class PresetEditor(QDialog):
    preset_saved = Signal(str, dict)  # Emits (Preset Name, Preset Data Mapping)

    def __init__(self, parent=None, preset_name="", preset_data=None):
        super().__init__(parent)
        self.setWindowTitle("Matrix Fretboard Preset Studio")
        self.setFixedSize(720, 520)
        self.setStyleSheet("background-color: #0e1014; color: #fff;")

        self.chords = preset_data.copy() if preset_data else {}
        self.active_chord_key = None
        self.string_names = ["E", "A", "D", "G", "B", "e"]

        # Local State Matrix Engine for editing current chord
        self.current_frets = [0, 0, 0, 0, 0, 0]
        self.start_fret = 1

        init_ui_layout = QHBoxLayout(self)

        # --- LEFT PANEL: LIST OF CHORDS IN PRESET ---
        left_box = QVBoxLayout()
        self.preset_title_input = QLineEdit(preset_name if preset_name else "My Custom Preset")
        self.preset_title_input.setStyleSheet(
            "background-color: #1a1c23; border: 1px solid #323645; padding: 6px; color: #fff; font-weight: bold;")
        left_box.addWidget(QLabel("Preset Name:"))
        left_box.addWidget(self.preset_title_input)

        left_box.addSpacing(10)
        left_box.addWidget(QLabel("Chords in Preset:"))
        self.chord_list_widget = QListWidget()
        self.chord_list_widget.setStyleSheet("background-color: #12141c; border: 1px solid #222530; color: #fff;")
        self.chord_list_widget.itemClicked.connect(self.load_selected_chord)
        left_box.addWidget(self.chord_list_widget)

        self.add_chord_btn = QPushButton("+ Add New Chord Slot")
        self.add_chord_btn.setStyleSheet("background-color: #242936; border: 1px solid #3a4257; padding: 6px;")
        self.add_chord_btn.clicked.connect(self.initiate_new_chord)
        left_box.addWidget(self.add_chord_btn)

        self.save_preset_btn = QPushButton("💾 SAVE COMPLETE PRESET")
        self.save_preset_btn.setStyleSheet(
            "background-color: #7856ff; font-weight: bold; padding: 10px; margin-top: 10px; border-radius: 4px;")
        self.save_preset_btn.clicked.connect(self.save_and_compile_preset)
        left_box.addWidget(self.save_preset_btn)

        init_ui_layout.addLayout(left_box, stretch=2)

        # --- RIGHT PANEL: THE SCHEMATIC INTERACTIVE FRETBOARD COMPOSER ---
        self.board_panel = QFrame()
        self.board_panel.setStyleSheet("background-color: #111319; border: 1px solid #232631; border-radius: 6px;")
        right_layout = QVBoxLayout(self.board_panel)

        # Chord Details Header
        header_layout = QHBoxLayout()
        self.chord_name_input = QLineEdit("A minor")
        self.chord_name_input.setStyleSheet(
            "font-size: 16px; font-weight: bold; background: transparent; border-bottom: 2px solid #7856ff; color: #fff;")
        header_layout.addWidget(QLabel("Chord:"))
        header_layout.addWidget(self.chord_name_input)
        right_layout.addLayout(header_layout)

        # Fretboard Body Horizontal Core Area
        fretboard_area = QHBoxLayout()
        self.canvas_view = FretboardCanvas(self)
        fretboard_area.addWidget(self.canvas_view, stretch=8)

        # Scroll Slider to scale frets vertically
        self.fret_slider = QSlider(Qt.Orientation.Vertical)
        self.fret_slider.setRange(1, 10)
        self.fret_slider.setValue(10)  # Top sets base range starting at Fret 1
        self.fret_slider.valueChanged.connect(self.handle_fret_scroll)
        fretboard_area.addWidget(self.fret_slider, stretch=1)

        right_layout.addLayout(fretboard_area)

        # Matrix Field Display Array
        display_layout = QHBoxLayout()
        self.string_toggle_btns = []
        self.matrix_lbls = []

        for idx, item in enumerate(self.string_names):
            col = QVBoxLayout()
            btn = QPushButton(item)
            btn.setFixedWidth(32)
            btn.setStyleSheet(
                "background-color: #1c1e24; font-weight: bold; color: #4ba3e3; border: 1px solid #313543;")
            btn.clicked.connect(lambda checked=False, i=idx: self.toggle_string_mute(i))
            col.addWidget(btn)

            lbl = QLabel("0")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                "font-family: 'Consolas'; font-size: 14px; font-weight: bold; color: #eedd82; margin-top: 4px;")
            col.addWidget(lbl)

            self.string_toggle_btns.append(btn)
            self.matrix_lbls.append(lbl)
            display_layout.addLayout(col)

        right_layout.addLayout(display_layout)

        # Direct Numerical Entry Input Matrix Field Box
        manual_layout = QHBoxLayout()
        self.manual_fret_input = QLineEdit("0 2 2 1 0 0")
        self.manual_fret_input.setStyleSheet(
            "background-color: #1a1c23; border: 1px solid #323645; padding: 6px; color: #fff; font-family: 'Consolas';")
        self.manual_fret_input.textChanged.connect(self.handle_manual_text_entry)
        manual_layout.addWidget(QLabel("Type Array:"))
        manual_layout.addWidget(self.manual_fret_input)
        right_layout.addLayout(manual_layout)

        # Keybind Setup Fields
        bind_layout = QHBoxLayout()
        self.keybind_input = QLineEdit("1")
        self.keybind_input.setMaxLength(1)
        self.keybind_input.setFixedWidth(50)
        self.keybind_input.setStyleSheet(
            "background-color: #1a1c23; border: 1px solid #323645; padding: 4px; color: #fff; text-align: center; font-weight: bold;")
        bind_layout.addWidget(QLabel("Key Assigned to Chord:"))
        bind_layout.addWidget(self.keybind_input)

        self.commit_chord_btn = QPushButton("💾 Keep Chord")
        self.commit_chord_btn.setStyleSheet(
            "background-color: #1db954; font-weight: bold; color:#fff; padding: 6px 15px;")
        self.commit_chord_btn.clicked.connect(self.commit_current_chord_to_memory)
        bind_layout.addWidget(self.commit_chord_btn)

        right_layout.addLayout(bind_layout)
        init_ui_layout.addWidget(self.board_panel, stretch=3)

        self.refresh_chord_list_view()
        if self.chords:
            self.active_chord_key = list(self.chords.keys())[0]
            self.load_active_chord_into_gui()

    def handle_fret_scroll(self, val):
        self.start_fret = 11 - val  # Inverts value so scrolling up climbs higher frets
        self.canvas_view.update()

    def toggle_string_mute(self, idx):
        self.current_frets[idx] = -1 if self.current_frets[idx] != -1 else 0
        self.update_matrix_views()

    def update_matrix_views(self):
        for i in range(6):
            val = self.current_frets[i]
            self.matrix_lbls[i].setText("X" if val == -1 else str(val))
        self.manual_fret_input.blockSignals(True)
        self.manual_fret_input.setText(" ".join(str(x) for x in self.current_frets))
        self.manual_fret_input.blockSignals(False)
        self.canvas_view.update()

    def handle_manual_text_entry(self, text):
        try:
            tokens = text.strip().split()
            if len(tokens) == 6:
                self.current_frets = [int(t) for t in tokens]
                self.update_matrix_views()
        except ValueError:
            pass

    def initiate_new_chord(self):
        self.active_chord_key = None
        self.chord_name_input.setText("New Chord")
        self.keybind_input.setText("")
        self.current_frets = [0, 0, 0, 0, 0, 0]
        self.update_matrix_views()

    def commit_current_chord_to_memory(self):
        name = self.chord_name_input.text().strip()
        kb = self.keybind_input.text().strip()
        if not name or not kb:
            QMessageBox.warning(self, "Incomplete Parameters",
                                "Please fill out a unique Chord Name and single Keybind.")
            return

        # Remove old reference if updating key
        if self.active_chord_key and self.active_chord_key != kb:
            if self.active_chord_key in self.chords:
                del self.chords[self.active_chord_key]

        self.chords[kb] = {"name": name, "frets": list(self.current_frets)}
        self.active_chord_key = kb
        self.refresh_chord_list_view()

    def refresh_chord_list_view(self):
        self.chord_list_widget.clear()
        for kb, info in self.chords.items():
            self.chord_list_widget.addItem(f"[{kb}] — {info['name']} ({info['frets']})")

    def load_selected_chord(self, item):
        text = item.text()
        kb = text.split("]")[0].replace("[", "").strip()
        self.active_chord_key = kb
        self.load_active_chord_into_gui()

    def load_active_chord_into_gui(self):
        if self.active_chord_key in self.chords:
            info = self.chords[self.active_chord_key]
            self.chord_name_input.setText(info["name"])
            self.keybind_input.setText(self.active_chord_key)
            self.current_frets = list(info["frets"])
            self.update_matrix_views()

    def save_and_compile_preset(self):
        title = self.preset_title_input.text().strip()
        if not title or not self.chords:
            QMessageBox.warning(self, "Empty Preset", "Please add at least one chord to save this preset.")
            return
        self.preset_saved.emit(title, self.chords)
        self.accept()


class FretboardCanvas(QWidget):
    def __init__(self, editor: PresetEditor):
        super().__init__(editor)
        self.editor = editor
        self.setMinimumHeight(240)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        margin_left, margin_right = 40, 40
        margin_top, margin_bottom = 30, 30

        # Draw 4 sequential frets based on scroll index
        fret_cols = 4
        fret_w = (w - margin_left - margin_right) / fret_cols
        string_h = (h - margin_top - margin_bottom) / 5

        # Draw Wood Fret Grid Background
        painter.setPen(QPen(QColor("#2d3240"), 1))
        for f in range(fret_cols + 1):
            cx = margin_left + f * fret_w
            painter.drawLine(cx, margin_top, cx, h - margin_bottom)
            if f < fret_cols:
                fret_num = self.editor.start_fret + f
                painter.drawText(cx + fret_w / 2 - 5, margin_top - 10, str(fret_num))

        # Draw Strings
        for s in range(6):
            cy = margin_top + s * string_h
            painter.setPen(QPen(QColor("#525a70"), 2 if s < 3 else 1))
            painter.drawLine(margin_left, cy, w - margin_right, cy)

        # Plot Active Fret Nodes
        for s in range(6):
            f_val = self.editor.current_frets[s]
            if f_val >= self.editor.start_fret and f_val < self.editor.start_fret + fret_cols:
                f_idx = f_val - self.editor.start_fret
                cx = margin_left + f_idx * fret_w + fret_w / 2
                cy = margin_top + s * string_h
                painter.setBrush(QBrush(QColor("#ff4878")))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(cx - 7, cy - 7, 14, 14)

    def mousePressEvent(self, event):
        w, h = self.width(), self.height()
        margin_left, margin_right = 40, 40
        margin_top, margin_bottom = 30, 30

        fret_cols = 4
        fret_w = (w - margin_left - margin_right) / fret_cols
        string_h = (h - margin_top - margin_bottom) / 5

        ex, ey = event.position().x(), event.position().y()

        # Map mouse coordinates back into the discrete pitch array matrix
        closest_string = clip_idx = int(round((ey - margin_top) / string_h))
        closest_string = max(0, min(5, closest_string))

        if margin_left <= ex <= (w - margin_right):
            f_idx = int((ex - margin_left) // fret_w)
            target_fret = self.editor.start_fret + f_idx
            # If clicked directly on the existing node, clear it back to open string (0)
            if self.editor.current_frets[closest_string] == target_fret:
                self.editor.current_frets[closest_string] = 0
            else:
                self.editor.current_frets[closest_string] = target_fret
            self.editor.update_matrix_views()