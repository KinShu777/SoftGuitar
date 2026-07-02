import queue
import sounddevice as sd
import numpy as np

_STRING_PARAMS = [
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


def _make_body_ir(sr: int, length_ms: float = 28.0) -> np.ndarray:
    n = int(sr * length_ms / 1000)
    t = np.linspace(0, length_ms / 1000, n, endpoint=False)
    ir = 0.55 * np.sin(2 * np.pi * 180 * t) * np.exp(-t / 0.018)
    ir += 0.30 * np.sin(2 * np.pi * 390 * t) * np.exp(-t / 0.010)
    ir += 0.15 * np.sin(2 * np.pi * 780 * t) * np.exp(-t / 0.005)
    ir /= np.max(np.abs(ir) + 1e-9)
    return ir.astype(np.float32)


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


class AudioEngine:
    def __init__(self, sample_rate=44100):
        self.sample_rate = sample_rate
        self.event_queue = queue.Queue()
        self.open_frequencies = [82.41, 110.00, 146.83, 196.00, 246.94, 329.63]
        self.current_frequencies = list(self.open_frequencies)

        # Pre-allocated maximum delay line arrays to handle structural upper bounds
        self.max_delay_size = int(sample_rate / 40.0)  # Safe buffer down to a low 40Hz note
        self.ring_buffers = np.zeros((6, self.max_delay_size), dtype=np.float32)
        self.buffer_lengths = np.zeros(6, dtype=np.int32)
        self.buffer_pointers = np.zeros(6, dtype=np.int32)

        # PRE-ALLOCATED NOISE RESERVOIRS (Pure Zero-Allocation System)
        self.noise_pool_size = 44100
        self.raw_noise_pool = np.random.uniform(-1.0, 1.0, self.noise_pool_size).astype(np.float32)
        self.soft_noise_pool = np.convolve(self.raw_noise_pool, np.ones(3) / 3, mode='same').astype(np.float32)
        self.noise_index = 0

        # State tracking matrices
        self.string_active = np.zeros(6, dtype=bool)
        self.string_decay = np.zeros(6, dtype=np.float32)
        self.string_S = np.zeros(6, dtype=np.float32)

        # Pre-allocated convolution overlap and mixer buffers
        self._ir = _make_body_ir(sample_rate)
        self._ir_overlap = np.zeros(len(self._ir) - 1, dtype=np.float32)

        # Pre-allocate a steady workspace accumulation buffer for safe overlap addition
        self.accum_buffer = np.zeros(256 + len(self._ir) - 1, dtype=np.float32)
        self.mix_buffer = np.zeros(256, dtype=np.float32)
        self.iir_buffer = np.zeros(256, dtype=np.float32)

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
        for i, fret in enumerate(fret_positions):
            if fret == -1:
                self.current_frequencies[i] = 0.0
            else:
                self.current_frequencies[i] = self.open_frequencies[i] * (2.0 ** (fret / 12.0))

    def trigger_pluck(self, string_idx, pressure):
        if self.current_frequencies[string_idx] > 0:
            self.event_queue.put((string_idx, float(np.clip(pressure, 0.1, 1.0))))

    def _audio_callback(self, outdata, frames, time, status):
        # Clear out main mixing buffer in-place
        self.mix_buffer.fill(0.0)

        # --- PROCESS PLUCK EVENTS ---
        while not self.event_queue.empty():
            idx, vel = self.event_queue.get_nowait()
            freq = self.current_frequencies[idx]
            if freq == 0.0: continue

            buf_size = int(self.sample_rate / freq)
            if buf_size > self.max_delay_size: buf_size = self.max_delay_size

            self.buffer_lengths[idx] = buf_size
            self.buffer_pointers[idx] = 0

            start_p = self.noise_index
            end_p = start_p + buf_size

            pool = self.soft_noise_pool if vel < 0.6 else self.raw_noise_pool

            if end_p < self.noise_pool_size:
                self.ring_buffers[idx, :buf_size] = pool[start_p:end_p] * vel
                self.noise_index = end_p
            else:
                rem = self.noise_pool_size - start_p
                self.ring_buffers[idx, :rem] = pool[start_p:] * vel
                self.ring_buffers[idx, rem:buf_size] = pool[:buf_size - rem] * vel
                self.noise_index = buf_size - rem

            self.string_S[idx] = _S[idx]
            self.string_decay[idx] = _DBASE[idx] + vel * _DVEL[idx]
            self.string_active[idx] = True

        # --- REAL-TIME WAVEGUIDE CORE LOOP ---
        for i in range(6):
            if not self.string_active[i]: continue

            buf_len = self.buffer_lengths[i]
            ptr = self.buffer_pointers[i]
            dec = self.string_decay[i]
            Sc = self.string_S[i]
            Sc1 = 1.0 - Sc

            for f in range(frames):
                cur = self.ring_buffers[i, ptr]
                nxt_ptr = (ptr + 1) % buf_len
                nxt = self.ring_buffers[i, nxt_ptr]

                self.mix_buffer[f] += cur
                self.ring_buffers[i, ptr] = (Sc * cur + Sc1 * nxt) * dec
                ptr = nxt_ptr

            self.buffer_pointers[i] = ptr
            if np.max(np.abs(self.ring_buffers[i, :buf_len])) < 0.0004:
                self.string_active[i] = False

        # --- PROCESS RESONANCE CHAIN IN-PLACE ---
        np.copyto(self.iir_buffer, self.mix_buffer)

        for k, (b, a) in enumerate(self._iir_sections):
            w1, w2 = self._iir_states[k]
            for n in range(frames):
                w0 = self.iir_buffer[n] - a[1] * w1 - a[2] * w2
                self.iir_buffer[n] = b[0] * w0 + b[1] * w1 + b[2] * w2
                w2, w1 = w1, w0
            self._iir_states[k] = [w1, w2]

        # --- ZERO-ALLOCATION OVERLAP-ADD SYSTEM ---
        self.accum_buffer.fill(0.0)
        # 1. Load the previous block's tail overlap directly into the tracking matrix
        self.accum_buffer[:len(self._ir_overlap)] += self._ir_overlap

        # 2. Convolve current frame blocks
        full_conv = np.convolve(self.mix_buffer, self._ir).astype(np.float32)
        self.accum_buffer[:len(full_conv)] += full_conv

        # 3. Pull out the clean output frame segment safely
        body_ir_conv = self.accum_buffer[:frames]

        # 4. Cache the leftover ring-out tail directly into the permanent overlap state array
        self._ir_overlap[:] = self.accum_buffer[frames:frames + len(self._ir_overlap)]

        # --- HEADROOM MIXING & COMPRESSION ---
        for f in range(frames):
            val = (self.mix_buffer[f] * 0.45 + self.iir_buffer[f] * 0.35 + body_ir_conv[f] * 0.20) * 0.38
            if abs(val) > 0.25:
                val = np.sign(val) * (0.25 + 0.75 * np.tanh((abs(val) - 0.25) / 0.75))
            outdata[f, 0] = val