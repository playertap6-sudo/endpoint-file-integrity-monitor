"""
gui/sounds.py
Memory-synthesized sound effects engine using Python standard library:
math, struct, wave, io, winsound, threading.

Generates soft, clean 16-bit 44.1kHz WAV audio in memory once at startup
and stores the bytes in a module-level dictionary to prevent garbage collection.
Plays asynchronously via winsound.PlaySound with graceful winsound.Beep fallback.
"""

import io
import math
import struct
import wave
import threading

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

# Module-level dictionary storing generated WAV byte buffers permanently
_GLOBAL_WAV_CACHE = {}
_GLOBAL_READY = False
_INIT_LOCK = threading.Lock()
_INIT_STARTED = False
_ERROR_LOGGED = False
SAMPLE_RATE = 44100


def _build_wav(samples: list[float]) -> bytes:
    """Converts normalized float samples (-1.0 to 1.0) into a 16-bit PCM WAV in memory."""
    try:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)      # Mono
            wf.setsampwidth(2)      # 16-bit
            wf.setframerate(SAMPLE_RATE)
            packed = bytearray()
            for s in samples:
                val = max(-1.0, min(1.0, s))
                packed.extend(struct.pack("<h", int(val * 32767.0)))
            wf.writeframes(packed)
        return buf.getvalue()
    except Exception as e:
        print(f"[Sound Error] Failed to pack WAV: {e}")
        return b""


def _generate_tone(freq: float, duration_s: float, volume: float = 0.60,
                   decay: float = 10.0, attack_ms: float = 8.0) -> list[float]:
    """Generates a sine wave tone with fast attack and exponential decay envelope."""
    num_samples = int(SAMPLE_RATE * duration_s)
    attack_samples = max(1, int(SAMPLE_RATE * (attack_ms / 1000.0)))
    samples = []

    for i in range(num_samples):
        t = i / SAMPLE_RATE
        raw = math.sin(2.0 * math.pi * freq * t)

        if i < attack_samples:
            env = (i / attack_samples)
        else:
            env = math.exp(-decay * (t - attack_ms / 1000.0))

        samples.append(raw * env * volume)
    return samples


def _init_global_sounds():
    """Generates all sound waveforms once in background with amplitude ~0.60."""
    global _GLOBAL_WAV_CACHE, _GLOBAL_READY
    if _GLOBAL_READY:
        return

    try:
        # 1. Alert: two quick rising tones, a warning chime (520 Hz -> 880 Hz)
        t1 = _generate_tone(520.0, 0.12, volume=0.60, decay=8.0)
        p1 = [0.0] * int(SAMPLE_RATE * 0.03)
        t2 = _generate_tone(880.0, 0.20, volume=0.62, decay=6.0)
        _GLOBAL_WAV_CACHE["alert"] = _build_wav(t1 + p1 + t2)

        # 2. Suspect Found: quick two-tone alerting chime (620 Hz -> 490 Hz)
        sf1 = _generate_tone(620.0, 0.10, volume=0.58, decay=10.0)
        sfp = [0.0] * int(SAMPLE_RATE * 0.02)
        sf2 = _generate_tone(490.0, 0.16, volume=0.60, decay=7.0)
        _GLOBAL_WAV_CACHE["suspect_found"] = _build_wav(sf1 + sfp + sf2)

        # 3. Process Killed: short low 'thud' followed by bright high ping
        thud = []
        thud_samples = int(SAMPLE_RATE * 0.08)
        for i in range(thud_samples):
            t = i / SAMPLE_RATE
            f = 140.0 - 90.0 * (i / thud_samples)
            env = math.exp(-22.0 * t)
            thud.append(math.sin(2.0 * math.pi * f * t) * env * 0.60)

        ping_pause = [0.0] * int(SAMPLE_RATE * 0.03)
        ping = _generate_tone(1760.0, 0.16, volume=0.58, decay=12.0)
        _GLOBAL_WAV_CACHE["process_killed"] = _build_wav(thud + ping_pause + ping)

        # 4. Restore Done: pleasant three-note ascending chime (C5 -> E5 -> G5)
        n1 = _generate_tone(523.25, 0.10, volume=0.58, decay=10.0)
        n2 = _generate_tone(659.25, 0.10, volume=0.60, decay=10.0)
        n3 = _generate_tone(783.99, 0.22, volume=0.62, decay=5.0)
        _GLOBAL_WAV_CACHE["restore_done"] = _build_wav(n1 + n2 + n3)

        # 5. Scan Done: one soft clean click (only played if changed files exist)
        click_samples = int(SAMPLE_RATE * 0.03)
        click = []
        for i in range(click_samples):
            t = i / SAMPLE_RATE
            env = math.exp(-80.0 * t)
            click.append(math.sin(2.0 * math.pi * 920.0 * t) * env * 0.58)
        _GLOBAL_WAV_CACHE["scan_done"] = _build_wav(click)

        # 6. Baseline Done & Accept Changes: soft two-note confirmation (D5 -> A5)
        b1 = _generate_tone(587.33, 0.10, volume=0.58, decay=12.0)
        b2 = _generate_tone(880.00, 0.18, volume=0.60, decay=7.0)
        conf_wav = _build_wav(b1 + b2)
        _GLOBAL_WAV_CACHE["baseline_done"] = conf_wav
        _GLOBAL_WAV_CACHE["accept_changes"] = conf_wav

        _GLOBAL_READY = True
    except Exception as e:
        print(f"[Sound Error] Failed generating waveforms: {e}")


def start_sound_generation():
    """Starts background generation of WAV data once (daemon)."""
    global _INIT_STARTED
    with _INIT_LOCK:
        if _INIT_STARTED:
            return
        _INIT_STARTED = True
        t = threading.Thread(target=_init_global_sounds, daemon=True)
        t.start()


class SoundManager:
    """Manages playback of synthesized procedural sound effects."""

    def __init__(self, db_manager=None):
        self.db = db_manager
        self.enabled = True
        self._wav_cache = _GLOBAL_WAV_CACHE
        self.wav_cache = _GLOBAL_WAV_CACHE

        # Generate WAV data in background thread at startup
        start_sound_generation()

        if self.db:
            try:
                setting_val = self.db.get_setting("sound_effects", "true")
                self.enabled = str(setting_val).lower() != "false"
            except Exception:
                self.enabled = True

    def is_ready(self) -> bool:
        """Returns True if background sound generation has finished."""
        return _GLOBAL_READY

    def set_enabled(self, enabled: bool):
        """Enables or disables sound output."""
        self.enabled = bool(enabled)

    def _beep_fallback(self, sound_name: str):
        """Fallback tone using winsound.Beep executed in a background thread."""
        freq_map = {
            "alert": [(520, 120), (880, 200)],
            "suspect_found": [(620, 100), (490, 160)],
            "process_killed": [(120, 80), (1760, 150)],
            "restore_done": [(523, 100), (659, 100), (784, 200)],
            "scan_done": [(900, 40)],
            "baseline_done": [(587, 100), (880, 180)],
            "accept_changes": [(587, 100), (880, 180)],
        }
        beeps = freq_map.get(sound_name, [(800, 100)])
        for freq, dur in beeps:
            try:
                winsound.Beep(freq, dur)
            except Exception:
                pass

    def play(self, sound_name: str):
        """
        Plays the requested sound asynchronously without blocking.
        Does nothing until background WAV generation is ready.
        """
        global _ERROR_LOGGED
        if not _GLOBAL_READY or not self.enabled or not HAS_WINSOUND:
            return

        data = _GLOBAL_WAV_CACHE.get(sound_name)
        if not data:
            return

        try:
            winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_ASYNC)
        except Exception:
            # Fall back to playing SND_MEMORY in a daemon background thread
            try:
                threading.Thread(
                    target=winsound.PlaySound,
                    args=(data, winsound.SND_MEMORY),
                    daemon=True
                ).start()
            except Exception as e:
                print(f"[Sound Error] winsound.PlaySound failed for '{sound_name}': {e}")
                if not _ERROR_LOGGED and self.db:
                    _ERROR_LOGGED = True
                    try:
                        self.db.log_activity("SOUND_ERROR", f"Audio device error on '{sound_name}': {str(e)[:100]}")
                    except Exception:
                        pass
                threading.Thread(target=self._beep_fallback, args=(sound_name,), daemon=True).start()
