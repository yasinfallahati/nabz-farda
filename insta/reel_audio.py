"""reel_audio.py — self-synthesised (copyright-free) 120 BPM track + whoosh/impact SFX for the v2 reel.
Pure numpy. music(total, cuts, outro_start, path) writes a 44.1 kHz stereo 16-bit WAV."""
import numpy as np, wave

SR = 44100
CHORDS = [  # Am - F - C - G  (bass root, chord tones)
    (55.00, [220.00, 261.63, 329.63]),
    (43.65, [174.61, 220.00, 261.63]),
    (65.41, [261.63, 329.63, 392.00]),
    (49.00, [196.00, 246.94, 293.66]),
]

def _t(d): return np.arange(int(d * SR)) / SR

def _band(x, lo=None, hi=None, soft=0.15):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR); m = np.ones_like(f)
    if lo: m *= 1 / (1 + np.exp(-(f - lo) / (lo * soft)))
    if hi: m *= 1 / (1 + np.exp((f - hi) / (hi * soft)))
    return np.fft.irfft(X * m, len(x))

def _saw(freq, t, maxf=5000, tilt=1.0, detune=(0.0,)):
    out = np.zeros_like(t)
    for dc in detune:
        f = freq * 2 ** (dc / 1200)
        for k in range(1, int(maxf / f) + 1):
            out += np.sin(2 * np.pi * k * f * t + k * 0.7) / k ** tilt
    return out / len(detune)

def _onepole_sweep(x, cut):
    """time-varying one-pole lowpass (cut = array of cutoff Hz)."""
    a = 1 - np.exp(-2 * np.pi * cut / SR); y = np.empty_like(x); s = 0.0
    for i in range(len(x)):
        s += a[i] * (x[i] - s); y[i] = s
    return y

class Track:
    def __init__(self, total):
        self.N = int((total + 2) * SR); self.total = total
        self.bus = {k: np.zeros((2, self.N)) for k in ("drums", "music", "fx")}
    def add(self, bus, sig, t0, gain=1.0, pan=0.0):
        i = int(round(t0 * SR))
        if i >= self.N or t0 < 0 and -t0 * SR >= len(sig): return
        if i < 0: sig, i = sig[-i:], 0
        s = sig[: self.N - i] * gain
        a = (pan + 1) * np.pi / 4
        self.bus[bus][0, i:i + len(s)] += s * np.cos(a) * 1.414
        self.bus[bus][1, i:i + len(s)] += s * np.sin(a) * 1.414

def music(total, cuts, outro_start, path, bpm=120, seed=7, pops=()):
    rng = np.random.default_rng(seed)
    b = 60 / bpm; s16 = b / 4; bar = 4 * b
    tr = Track(total)
    # ---- samples
    t = _t(0.45); f = 46 + 130 * np.exp(-t * 32)
    kick = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7) + 0.25 * _band(rng.standard_normal(len(t)), 2000) * np.exp(-t * 350)
    kick = np.tanh(kick * 1.8) * 0.9
    t = _t(0.35); n = rng.standard_normal(len(t))
    env = sum(np.exp(-np.clip(t - d, 0, None) * 160) * (t >= d) for d in (0, 0.011, 0.023)) * 0.6 + np.exp(-t * 20) * (t >= 0.023) * 0.6
    clap = _band(n, 900, 6000) * env
    t = _t(0.06); hat = _band(rng.standard_normal(len(t)), 7500) * np.exp(-t * 85)
    t = _t(0.35); ohat = _band(rng.standard_normal(len(t)), 6500) * np.exp(-t * 13)
    # ---- arrangement
    nbeats = int(np.ceil(outro_start / b))
    for k in range(nbeats):
        tb = k * b
        tr.add("drums", kick, tb, 1.0)
        if k % 2 == 1: tr.add("drums", clap, tb, 0.55)
        for q in range(4):
            if tb >= 2 * b or q % 2 == 0:  # 8ths in the first beats, 16ths after
                vel = [0.35, 0.18, 0.28, 0.2][q] * (1.0 if tb >= bar / 2 else 0.8)
                tr.add("drums", hat, tb + q * s16, vel, pan=0.25 if q % 2 else -0.15)
        if tb >= bar / 2: tr.add("drums", ohat, tb + 2 * s16, 0.16, pan=-0.3)
    # bass: rolling 16ths (skip the kick 16th), octave pop on the last 16th of every 2nd beat
    cache = {}
    def bassnote(fr, d):
        key = (fr, d)
        if key not in cache:
            t = _t(d); e = np.minimum(1, t / 0.004) * np.exp(-t * 9)
            cache[key] = (0.55 * _saw(fr, t, 1400, 1.25) + 0.7 * np.sin(2 * np.pi * fr * t)) * e
        return cache[key]
    for k in range(nbeats):
        tb = k * b; root = CHORDS[int(tb // bar) % 4][0]
        for q in (1, 2, 3):
            fr = root * (2 if (q == 3 and k % 2) else 1)
            tr.add("music", bassnote(fr * 2, s16 * 0.95), tb + q * s16, 0.42)
    # stabs (syncopated) + arp + pad
    def stab(ch, d, bright=3200):
        key = ("st", tuple(ch), d, bright)
        if key not in cache:
            t = _t(d); e = np.minimum(1, t / 0.003) * np.exp(-t * (6 if d < 0.6 else 1.6))
            cache[key] = sum(_saw(fr, t, bright, 1.15, (-9, 0, 9)) for fr in ch) * e / len(ch)
        return cache[key]
    for bi in range(int(np.ceil(outro_start / bar))):
        t0 = bi * bar; ch = CHORDS[bi % 4][1]
        if t0 >= bar / 2 - 1e-6 or True:
            for q in (0, 3, 6, 10, 14):
                tt = t0 + q * s16
                if tt < outro_start - 0.01 and tt >= b * 2 - 1e-6 or (tt < b * 2 and q in (0,)):
                    tr.add("music", stab(ch, 0.22), tt, 0.33, pan=0.2 if q % 2 else -0.2)
        # arp
        if t0 >= bar / 2:
            seq = [ch[0] * 2, ch[1] * 2, ch[2] * 2, ch[1] * 2]
            for q in range(16):
                tt = t0 + q * s16
                if tt >= outro_start: break
                fr = seq[q % 4]; tp = _t(0.18)
                pl = (np.sin(2 * np.pi * fr * tp) + 0.3 * np.sin(4 * np.pi * fr * tp)) * np.exp(-tp * 16)
                tr.add("music", pl, tt, 0.07, pan=0.5 * np.sin(q * 0.9))
    # pad through the whole thing (incl. outro)
    for bi in range(int(np.ceil(total / bar)) + 1):
        t0 = bi * bar; ch = CHORDS[bi % 4][1]; tp = _t(bar + 0.3)
        e = np.minimum(1, tp / 0.25) * np.minimum(1, np.clip(bar + 0.3 - tp, 0, None) / 0.3)
        pad = sum(np.sin(2 * np.pi * fr / 2 * tp) + 0.4 * np.sin(2 * np.pi * fr * 1.003 * tp) for fr in ch) * e
        tr.add("music", pad, t0, 0.07)
    # outro: final long chord + reverse-ish swell
    ch = CHORDS[int(outro_start // bar) % 4][1]
    tr.add("music", stab(ch, 2.6, 2400), outro_start, 0.5)
    tr.add("music", bassnote(CHORDS[int(outro_start // bar) % 4][0] * 2, 1.2), outro_start, 0.6)
    # ---- sidechain pump on the music bus
    tt = np.arange(tr.N) / SR
    sc = 1 - 0.65 * np.exp(-np.mod(tt, b) * 11) * (tt < outro_start)
    tr.bus["music"] *= sc
    # simple stereo delay for space
    m = tr.bus["music"]; d1, d2 = int(3 * s16 * SR), int(4 * s16 * SR)
    m[0, d1:] += 0.22 * m[1, :-d1]; m[1, d2:] += 0.18 * m[0, :-d2]
    # ---- FX: whoosh into every cut, impact on it
    for ci, c in enumerate(cuts):
        d = 0.55; t = _t(d); pk = 0.42
        x = rng.standard_normal(len(t))
        cut = np.where(t < pk, 400 + 7000 * (t / pk) ** 2, 7400 * np.exp(-(t - pk) * 22) + 300)
        w = _onepole_sweep(x, cut)
        w = w * np.where(t < pk, (t / pk) ** 2.2, np.exp(-(t - pk) * 18))
        w /= np.abs(w).max() + 1e-9
        direction = 1 if ci % 2 == 0 else -1
        # pan sweep: split into chunks
        ch = 8; L = len(w) // ch
        for j in range(ch):
            tr.add("fx", w[j * L:(j + 1) * L], c - pk + j * L / SR, 0.55, pan=direction * (-0.8 + 1.6 * j / (ch - 1)))
        big = ci in (0, len(cuts) - 1)
        t = _t(1.4 if big else 0.6); f = 38 + 70 * np.exp(-t * 10)
        imp = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * (3 if big else 8))
        imp += _band(rng.standard_normal(len(t)), None, 1800) * np.exp(-t * 14) * 0.8
        tr.add("fx", imp, c, 0.7 if big else 0.32)
        # tiny bright "tick" on the cut
        tp = _t(0.05); tr.add("fx", _band(rng.standard_normal(len(tp)), 4000) * np.exp(-tp * 120), c, 0.25)
    # UI "pop" blips (e.g. callouts appearing)
    for pt in pops:
        t = _t(0.12); f = 1500 * np.exp(-t * 18) + 600
        blip = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 38)
        tr.add("fx", blip, pt, 0.28, pan=0.0)
        tr.add("fx", _band(rng.standard_normal(len(t)), 3000) * np.exp(-t * 90), pt, 0.12)
    # opening hit at t=0
    t = _t(1.2); f = 40 + 90 * np.exp(-t * 9)
    tr.add("fx", np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.5), 0.0, 0.7)
    # ---- master
    mix = tr.bus["drums"] * 0.95 + tr.bus["music"] * 0.75 + tr.bus["fx"] * 0.7
    mix = mix[:, : int(total * SR)]
    tt = np.arange(mix.shape[1]) / SR
    mix *= np.minimum(1, (total - tt) / 0.6)            # short tail fade (loop-friendly)
    mix *= np.minimum(1, tt / 0.004)
    rms = np.sqrt(np.mean(mix ** 2)); mix *= 0.15 / (rms + 1e-9)
    mix = np.tanh(mix * 1.1) / np.tanh(1.1)
    mix *= 0.93 / (np.abs(mix).max() + 1e-9)
    pcm = (mix.T * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
    return path

if __name__ == "__main__":
    import sys, time
    t = time.time()
    music(30.0, [2.0, 7.0, 12.0, 17.0, 22.0, 27.0], 27.0, sys.argv[1] if len(sys.argv) > 1 else "/tmp/m.wav")
    print("ok", time.time() - t)
