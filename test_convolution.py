import numpy as np

# 1. Setup simulated parameters to match our real audio stream
frames = 256
ir_len = 1234

# Generate an identical mock incoming audio block and fake guitar body profile
mix_buffer = np.random.uniform(-1.0, 1.0, frames).astype(np.float32)
ir_original = np.random.uniform(-0.5, 0.5, ir_len).astype(np.float32)

print("--- Running Audio Equivalence Verification ---")

# --- METHOD A: Original np.convolve with historical carry-over loop ---
ir_overlap = np.zeros(ir_len - 1, dtype=np.float32)
accum = np.zeros(frames + ir_len - 1, dtype=np.float32)
accum[:ir_len - 1] += ir_overlap
full_conv = np.convolve(mix_buffer, ir_original)
accum[:len(full_conv)] += full_conv
output_method_A = accum[:frames].copy()

# --- METHOD B: Updated pre-allocated sliding dot product (Red's New Implementation) ---
ir_reversed = ir_original[::-1].copy() # Pre-reversed arrays enable direct dot products
conv_history = np.zeros(ir_len + frames, dtype=np.float32)
body_ir_conv = np.zeros(frames, dtype=np.float32)

# Feed input variables exactly as they pass inside the live audio callback
conv_history[ir_len - 1:ir_len - 1 + frames] = mix_buffer
for n in range(frames):
    body_ir_conv[n] = np.dot(conv_history[n:n + ir_len], ir_reversed)
output_method_B = body_ir_conv

# --- COMPARISON PHASE ---
# Calculate the maximum physical variance between the two waveforms
difference = np.max(np.abs(output_method_A - output_method_B))
print(f"Maximum Deviation Delta: {difference}")

# Assert that the threshold of error is practically non-existent
if difference < 1e-5:
    print("SUCCESS: Both algorithms produce mathematically identical audio streams!")
else:
    print("FAILURE: The audio mathematical behavior is mismatched!")