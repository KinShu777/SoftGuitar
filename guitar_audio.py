import queue
import sounddevice as sd
import numpy as np

# ---------------------------------------------------------------------------
# Per-string tuning parameters
# ---------------------------------------------------------------------------
_STRING_PARAMS = [
    # idx  S      decay_base  decay_vel
    (0, 0.505, 0.9940, 0.003),  # E2  82 Hz
    (1, 0.500, 0.9942, 0.003),  # A2  110 Hz
    (2, 0.495, 0.9945, 0.003),  # D3  147 Hz
    (3, 0.470, 0.9955, 0.002),  # G3  196 Hz
    (4, 0.440, 0.9965, 0.002),  # B3  247 Hz
    (5, 0.400, 0.9975, 0.001),  # e4  330 Hz
]
_S = np.array([p[1] for p in _STRING_PARAMS], dtype=np.float64)
_DBASE = np.array([p[2] for p in _STRING_PARAMS], dtype=np.float64)
_DVEL = np.array([p[3] for p in _STRING_PARAMS], dtype=np.float64)


# ---------------------------------------------------------------------------
# Synthetic body IR — models hollow-body wood/air resonance cavity
# ---------------------------------------------------------------------------
def _make_body_ir(sr: int, length_ms: float = 28.0) -> np.ndarray:
    n = int(sr * length_ms / 1000)
    t = np.linspace(0, length_ms / 1000, n, endpoint=False)
    ir = 0.55 * np.sin(2 * np.pi * 180 * t) * np.exp(-t / 0.018)
    ir += 0.30 * np.sin(2 * np.pi * 390 * t) * np.exp(-t / 0.010)
    ir += 0.15 * np.sin(2 * np.pi * 780 * t) * np.exp(-t / 0.005)
    ir /= np.max(np.abs(ir) + 1e-9)
    return ir.astype(np.float32)


# ---------------------------------------------------------------------------
# IIR 4-pole parametric body resonance cascade
# ---------------------------------------------------------------------------
def _biquad_coeffs(sr):
    def peak(fc, gain_db, Q):
        A = 10 ** (gain_db / 40)
        w0 = 2 * np.pi * fc / sr
        cw, sw = np.cos(w0), np.sin(w0)
        alpha = sw / (2 * Q)
        b0 = 1 + alpha * A;
        b1 = -2 * cw;
        b2 = 1 - alpha * A
        a0 = 1 + alpha / A;
        a1 = -2 * cw;
        a2 = 1 - alpha / A
        return np.array([b0, b1, b2]) / a0, np.array([1, a1 / a0, a2 / a0])

    def hishelf(fc, gain_db, S=0.9):
        A = 10 ** (gain_db / 40)
        w0 = 2 * np.pi * fc / sr
        cw = np.cos(w0);
        sw = np.sin(w0)
        alpha = sw / 2 * np.sqrt((A + 1 / A) * (1 / S - 1) + 2)
        sqA = np.sqrt(A)
        b0 = A * ((A + 1) + (A - 1) * cw + 2 * sqA * alpha)
        b1 = -2 * A * ((A - 1) + (A + 1) * cw)
        b2 = A * ((A + 1) + (A - 1) * cw - 2 * sqA * alpha)
        a0 = (A + 1) - (A - 1) * cw + 2 * sqA * alpha
        a1 = 2 * ((A - 1) - (A + 1) * cw)
        a2 = (A + 1) - (A - 1) * cw - 2 * sqA * alpha
        return np.array([b0, b1, b2]) / a0, np.array([1, a1 / a0, a2 / a0])

    b1, a1 = peak(180, 5.0, 3.5)
    b2, a2 = peak(390, 3.0, 4.0)
    b3, a3 = hishelf(4000, -4.0)
    return [(b1, a1), (b2, a2), (b3, a3)]


def _apply_biquad_cascade(x, sections, states):
    for k, (b, a) in enumerate(sections):
        w1, w2 = states[k]
        y = np.empty_like(x)
        for n in range(len(x)):
            w0 = x[n] - a[1] * w1 - a[2] * w2
            y[n] = b[0] * w0 + b[1] * w1 + b[2] * w2
            w2, w1 = w1, w0
        states[k] = [w1, w2]
        x = y
    return x


# ---------------------------------------------------------------------------
# Core Audio Engine Class
# ---------------------------------------------------------------------------
class AudioEngine:
    def __init__(self, sample_rate=44100):
        self.sample_rate = sample_rate
        self.event_queue = queue.Queue()

        # Base open string frequencies: E2, A2, D3, G3, B3, e4
        self.open_frequencies = [82.41, 110.00, 146.83, 196.00, 246.94, 329.63]
        self.current_frequencies = list(self.open_frequencies)

        # Base tuning offsets
        self.current_frets = [0, 0, 0, 0, 0, 0]
        self.capo_fret = 0

        self.active_strings = [None] * 6
        self._ir = _make_body_ir(sample_rate)
        self._ir_overlap = np.zeros(len(self._ir) - 1, dtype=np.float32)
        self._iir_sections = _biquad_coeffs(sample_rate)
        self._iir_states = [[0.0, 0.0] for _ in self._iir_sections]

        self.stream = sd.OutputStream(
            samplerate=sample_rate, channels=1,
            callback=self._audio_callback, blocksize=256,
            dtype='float32'
        )

    def start(self):
        self.stream.start()

    def stop(self):
        self.stream.stop()

    def set_chord(self, fret_positions):
        """Accepts an array like [0, 3, 2, 0, 1, 0] or [-1, 0, 2, 2, 1, 0]"""
        self.current_frets = fret_positions
        self._recalculate_pitches()

    def set_capo(self, fret):
        """Applies global capo pitch shift across all strings."""
        self.capo_fret = fret
        self._recalculate_pitches()

    def _recalculate_pitches(self):
        for i, fret in enumerate(self.current_frets):
            if fret == -1:
                self.current_frequencies[i] = 0.0
            else:
                total_fret = fret + self.capo_fret
                self.current_frequencies[i] = self.open_frequencies[i] * (2.0 ** (total_fret / 12.0))

    def trigger_pluck(self, string_idx, pressure):
        if self.current_frequencies[string_idx] > 0:
            self.event_queue.put((string_idx, float(np.clip(pressure, 0.1, 1.0))))

    def _audio_callback(self, outdata, frames, time, status):
        while not self.event_queue.empty():
            idx, vel = self.event_queue.get_nowait()
            freq = self.current_frequencies[idx]
            if freq == 0.0: continue

            buf_size = int(self.sample_rate / freq)
            noise = np.random.uniform(-1.0, 1.0, buf_size).astype(np.float32)
            if vel < 0.6:
                noise = np.convolve(noise, np.ones(3) / 3, mode='same').astype(np.float32)
            noise *= vel

            self.active_strings[idx] = [noise, 0, _DBASE[idx] + vel * _DVEL[idx], _S[idx], 0.0]

        buffer_out = np.zeros(frames, dtype=np.float32)
        for i in range(6):
            st = self.active_strings[i]
            if st is None: continue
            ring_buf, ptr, decay, S, _ = st
            buf_len = len(ring_buf)
            Sc, Sc1, dec = np.float32(S), np.float32(1.0 - S), np.float32(decay)

            for f in range(frames):
                cur = ring_buf[ptr]
                nxt_ptr = (ptr + 1) % buf_len
                buffer_out[f] += cur
                ring_buf[ptr] = (Sc * cur + Sc1 * ring_buf[nxt_ptr]) * dec
                ptr = nxt_ptr

            if np.max(np.abs(ring_buf)) < 0.0004:
                self.active_strings[i] = None
            else:
                self.active_strings[i][1] = ptr

        body_iir = _apply_biquad_cascade(buffer_out.copy(), self._iir_sections, self._iir_states)
        full_conv = np.convolve(buffer_out, self._ir).astype(np.float32)

        accum = np.zeros(max(len(self._ir_overlap), len(full_conv)), dtype=np.float32)
        accum[:len(self._ir_overlap)] += self._ir_overlap
        accum[:len(full_conv)] += full_conv
        body_ir_conv = accum[:frames]
        self._ir_overlap = accum[frames:frames + len(self._ir) - 1]

        final_mix = (buffer_out * 0.40 + body_iir * 0.35 + body_ir_conv * 0.25)

        # --- ANTI-COLLISION SOFT LIMITER ---
        for f in range(frames):
            val = final_mix[f] * 0.5
            if abs(val) > 0.25:
                val = np.sign(val) * (0.25 + 0.75 * np.tanh((abs(val) - 0.25) / 0.75))
            final_mix[f] = val

        outdata[:, 0] = np.clip(final_mix, -1.0, 1.0)