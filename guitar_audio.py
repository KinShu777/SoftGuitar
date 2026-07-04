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
    # Return reversed order to allow a direct dot-product sliding convolution
    return ir[::-1].astype(np.float32)


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
    CHORD_DICTIONARY = {
        "Open": [0, 0, 0, 0, 0, 0],
        "C Major": [-1, 3, 2, 0, 1, 0],
        "A Major": [-1, 0, 2, 2, 2, 0],
        "A Minor": [-1, 0, 2, 2, 1, 0],
        "G Major": [3, 2, 0, 0, 0, 3],
        "E Major": [0, 2, 2, 1, 0, 0],
        "E Minor": [0, 2, 2, 0, 0, 0],
        "D Major": [-1, -1, 0, 2, 3, 2],
        "D Minor": [-1, -1, 0, 2, 3, 1]
    }

    def __init__(self, sample_rate=44100):
        self.sample_rate = sample_rate
        self.event_queue = queue.Queue()
        self.open_frequencies = [82.41, 110.00, 146.83, 196.00, 246.94, 329.63]
        self.current_frequencies = list(self.open_frequencies)

        self.capo_fret = 0
        self.current_fret_positions = [0] * 6

        self.max_delay_size = int(sample_rate / 40.0)
        self.ring_buffers = np.zeros((6, self.max_delay_size), dtype=np.float32)
        self.buffer_lengths = np.zeros(6, dtype=np.int32)
        self.buffer_pointers = np.zeros(6, dtype=np.int32)

        self.ap_coeffs = np.zeros(6, dtype=np.float32)
        self.ap_x1 = np.zeros(6, dtype=np.float32)
        self.ap_y1 = np.zeros(6, dtype=np.float32)

        self.noise_pool_size = 44100
        self.raw_noise_pool = np.random.uniform(-1.0, 1.0, self.noise_pool_size).astype(np.float32)
        self.soft_noise_pool = np.convolve(self.raw_noise_pool, np.ones(3) / 3, mode='same').astype(np.float32)
        self.noise_index = 0

        self.string_active = np.zeros(6, dtype=bool)
        self.string_decay = np.zeros(6, dtype=np.float32)
        self.string_S = np.zeros(6, dtype=np.float32)
        self.palm_mute = 0.0
        # 0 = Disabled/Normal, 12 = 12th Fret Node, 7 = 7th Fret Node, 5 = 5th Fret Node
        self.harmonic_node = 0

        # --- ALLOCATION-FREE CONVOLUTION STORAGE ---
        # Note: _ir is pre-reversed in _make_body_ir to optimize dot products
        self._ir = _make_body_ir(sample_rate)
        self.ir_len = len(self._ir)

        # Pre-allocate input history buffer tracking line (IR length + block length)
        self.conv_history = np.zeros(self.ir_len + 256, dtype=np.float32)
        self.body_ir_conv = np.zeros(256, dtype=np.float32)

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

    def set_capo(self, fret):
        self.capo_fret = max(0, min(12, int(fret)))
        self._reapply_pitches()

    def set_chord(self, chord_input):
        if isinstance(chord_input, str):
            positions = self.CHORD_DICTIONARY.get(chord_input, [0, 0, 0, 0, 0, 0])
        else:
            positions = chord_input
        self.current_fret_positions = list(positions)
        self._reapply_pitches()

    def set_palm_mute(self, value):
        """Sets the global palm muting intensity value [0.0 to 1.0]."""
        self.palm_mute = float(np.clip(value, 0.0, 1.0))


    def _reapply_pitches(self):
        for i in range(6):
            fret = self.current_fret_positions[i]
            if fret == -1:
                self.current_frequencies[i] = 0.0
            else:
                total_frets = fret + self.capo_fret
                self.current_frequencies[i] = self.open_frequencies[i] * (2.0 ** (total_frets / 12.0))

    def trigger_pluck(self, string_idx, pressure):
        if self.current_frequencies[string_idx] > 0:
            self.event_queue.put((string_idx, float(np.clip(pressure, 0.1, 1.0))))

    def set_harmonic_node(self, node_value):
        """Sets the active natural harmonic fret node target.
        Supported options: 0 (disabled), 5, 7, 12
        """
        if node_value in [0, 5, 7, 12]:
            self.harmonic_node = int(node_value)
        else:
            self.harmonic_node = 0

    def _audio_callback(self, outdata, frames, time, status):
        self.mix_buffer.fill(0.0)

        # --- PROCESS PLUCK EVENTS ---
        while not self.event_queue.empty():
            idx, vel = self.event_queue.get_nowait()
            freq = self.current_frequencies[idx]
            if freq == 0.0: continue

            exact_period = self.sample_rate / freq
            int_period = int(exact_period)
            frac_period = exact_period - int_period

            if frac_period < 0.1:
                frac_period += 1.0
                int_period -= 1

            if int_period > self.max_delay_size: int_period = self.max_delay_size

            self.buffer_lengths[idx] = int_period
            self.buffer_pointers[idx] = 0

            self.ap_coeffs[idx] = (1.0 - frac_period) / (1.0 + frac_period)
            self.ap_x1[idx] = 0.0
            self.ap_y1[idx] = 0.0

            start_p = self.noise_index
            end_p = start_p + int_period
            pool = self.soft_noise_pool if vel < 0.6 else self.raw_noise_pool

            if end_p < self.noise_pool_size:
                self.ring_buffers[idx, :int_period] = pool[start_p:end_p] * vel
            node = self.harmonic_node

            # Fetch base excitation block matching the required period
            if end_p < self.noise_pool_size:
                excitation = pool[start_p:end_p].copy() * vel
                self.noise_index = end_p
            else:
                rem = self.noise_pool_size - start_p
                excitation = np.concatenate([pool[start_p:], pool[:int_period - rem]]) * vel
                self.noise_index = int_period - rem

            # Periodic Mode Suppression: Repeat a fractional pattern to isolate nodes across the full array
            if node > 0 and int_period > 8:
                if node == 12:
                    # 12th Fret (2nd Harmonic): Repeat a half-period pattern twice
                    half = int_period // 2
                    excitation[half:half * 2] = excitation[:half]
                elif node == 7:
                    # 7th Fret (3rd Harmonic): Repeat a third-period pattern three times
                    third = int_period // 3
                    excitation[third:third * 2] = excitation[:third]
                    excitation[third * 2:third * 3] = excitation[:third]
                elif node == 5:
                    # 5th Fret (4th Harmonic): Repeat a quarter-period pattern four times
                    quarter = int_period // 4
                    excitation[quarter:quarter * 2] = excitation[:quarter]
                    excitation[quarter * 2:quarter * 3] = excitation[:quarter]
                    excitation[quarter * 3:quarter * 4] = excitation[:quarter]

            self.ring_buffers[idx, :int_period] = excitation

            decay_mod = 0.0015 * (vel - 0.5)
            self.string_decay[idx] = float(np.clip(_DBASE[idx] + decay_mod, 0.985, 0.998))

            self.string_S[idx] = _S[idx]
            self.string_active[idx] = True

        # --- REAL-TIME WAVEGUIDE ENGINE ---
        pm = self.palm_mute
        for i in range(6):
            if not self.string_active[i]: continue

            buf_len = self.buffer_lengths[i]
            ptr = self.buffer_pointers[i]
            dec = self.string_decay[i] * (1.0 - pm * 0.12)
            Sc = self.string_S[i] * (1.0 - pm) + 0.5 * pm
            Sc1 = 1.0 - Sc

            ap_c = self.ap_coeffs[i]
            ax1 = self.ap_x1[i]
            ay1 = self.ap_y1[i]

            for f in range(frames):
                cur = self.ring_buffers[i, ptr]
                nxt_ptr = (ptr + 1) % buf_len
                nxt = self.ring_buffers[i, nxt_ptr]

                waveguide_sample = (Sc * cur + Sc1 * nxt) * dec
                fractional_sample = ap_c * waveguide_sample + ax1 - ap_c * ay1

                ax1 = waveguide_sample
                ay1 = fractional_sample

                self.mix_buffer[f] += fractional_sample
                self.ring_buffers[i, ptr] = fractional_sample
                ptr = nxt_ptr

            self.buffer_pointers[i] = ptr
            self.ap_x1[i] = ax1
            self.ap_y1[i] = ay1

            if np.max(np.abs(self.ring_buffers[i, :buf_len])) < 0.0004:
                self.string_active[i] = False

        # --- RESONANCE CHAIN (IIR) ---
        np.copyto(self.iir_buffer, self.mix_buffer)
        for k, (b, a) in enumerate(self._iir_sections):
            w1, w2 = self._iir_states[k]
            for n in range(frames):
                w0 = self.iir_buffer[n] - a[1] * w1 - a[2] * w2
                self.iir_buffer[n] = b[0] * w0 + b[1] * w1 + b[2] * w2
                w2, w1 = w1, w0
            self._iir_states[k] = [w1, w2]

        # --- ZERO-ALLOCATION SLIDING CONVOLUTION ---
        # 1. Shift old history components down to clear space at the end of the buffer
        self.conv_history[:self.ir_len - 1] = self.conv_history[frames:frames + self.ir_len - 1]

        # 2. Copy the fresh audio block directly into the available space
        self.conv_history[self.ir_len - 1:self.ir_len - 1 + frames] = self.mix_buffer

        # 3. Compute the sliding convolution using an allocation-free vector dot product loop
        for n in range(frames):
            self.body_ir_conv[n] = np.dot(self.conv_history[n:n + self.ir_len], self._ir)

        # --- FINAL MIX & LIMITER ---
        for f in range(frames):
            val = (self.mix_buffer[f] * 0.45 + self.iir_buffer[f] * 0.35 + self.body_ir_conv[f] * 0.20) * 0.38
            if abs(val) > 0.25:
                val = np.sign(val) * (0.25 + 0.75 * np.tanh((abs(val) - 0.25) / 0.75))
            outdata[f, 0] = val