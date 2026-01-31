import wave
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING

import numpy as np
import pyaudio
from numpy.typing import NDArray
from pydantic import BaseModel

if TYPE_CHECKING:
    from mxbi.theater import Theater


@dataclass
class StimulusSequenceUnit:
    frequency: int | None = None
    duration: int | None = None  # ms
    interval: int = 0  # ms
    stimulus: NDArray[np.int16] | None = None
    master_volume: int | None = None
    digital_volume: int | None = None


class ToneConfig(BaseModel):
    frequency: int
    duration: int  # ms


SAMPLE_RATE = 44100


@lru_cache(maxsize=128)
def _cached_wave_unit(frequency: int, duration: int) -> NDArray[np.int16]:
    samples = int(SAMPLE_RATE * (duration / 1000))
    if samples <= 0:
        return np.zeros(0, dtype=np.int16)

    t = np.arange(samples) / SAMPLE_RATE
    tone = np.sin(2 * np.pi * frequency * t)

    fade_samples = min(int(4.5 * SAMPLE_RATE / 1000), samples // 2)
    if fade_samples > 0:
        envelope = np.ones(samples)
        envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
        envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)
        tone *= envelope

    max_val = np.iinfo(np.int16).max
    return (tone * max_val).astype(np.int16)


class APlayer:
    def __init__(self, theater: "Theater") -> None:
        self._theater = theater
        self._executor = ThreadPoolExecutor(1)
        self._player = pyaudio.PyAudio()
        self._stop_event = Event()
        self._stream = self._player.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            output=True,
        )

    def _gen_wave_unit(self, tone_config: ToneConfig) -> NDArray[np.int16]:
        cached = _cached_wave_unit(
            tone_config.frequency,
            tone_config.duration,
        )
        return cached.copy()

    def _gen_stimulus_unit(self, unit: StimulusSequenceUnit) -> StimulusSequenceUnit:
        """Ensure a stimulus unit has waveform data while retaining volume metadata."""
        if unit.stimulus is not None:
            return StimulusSequenceUnit(
                frequency=unit.frequency,
                duration=unit.duration,
                interval=unit.interval,
                stimulus=unit.stimulus.copy(),
                master_volume=unit.master_volume,
                digital_volume=unit.digital_volume,
            )

        if unit.frequency is None or unit.duration is None:
            raise ValueError(
                "StimulusSequenceUnit requires frequency and duration when stimulus is not provided"
            )

        stimulus = self.generate_stimulus(
            [
                ToneConfig(frequency=unit.frequency, duration=unit.duration),
                ToneConfig(frequency=0, duration=unit.interval),
            ],
            1,
        )
        return StimulusSequenceUnit(
            frequency=unit.frequency,
            duration=unit.duration,
            interval=unit.interval,
            stimulus=stimulus,
            master_volume=unit.master_volume,
            digital_volume=unit.digital_volume,
        )

    def generate_stimulus(
        self, tone_config: list[ToneConfig], times: int
    ) -> NDArray[np.int16]:
        """Concatenate the configured tones and repeat them the requested number of times."""
        tone_unit = np.concatenate([self._gen_wave_unit(cfg) for cfg in tone_config])
        return np.tile(tone_unit, times)

    def generate_stimulus_sequence(
        self, units: list[StimulusSequenceUnit], duration: int
    ) -> list[StimulusSequenceUnit]:
        """Expand stimulus units to fill the target duration while supporting per-unit volume overrides."""
        unit_durations: list[int] = []
        for unit in units:
            if unit.duration is not None:
                unit_durations.append(unit.duration + unit.interval)
            elif unit.stimulus is not None:
                unit_ms = int(len(unit.stimulus) / SAMPLE_RATE * 1000)
                unit_durations.append(unit_ms)
            else:
                raise ValueError(
                    "StimulusSequenceUnit must define duration or stimulus before sequencing"
                )

        cycle_duration = sum(unit_durations)

        k, r = divmod(duration, cycle_duration)

        sequence = [self._gen_stimulus_unit(u) for _ in range(k) for u in units]

        for unit, dur in zip(units, unit_durations):
            if r >= dur:
                r -= dur
                sequence.append(self._gen_stimulus_unit(unit))
            else:
                break

        return sequence

    def _play_stimulus(self, stimulus: "NDArray[np.int16]"):
        """Internal helper for playback when no per-tone volume changes are needed."""
        data = stimulus.tobytes()
        chunk_size = 1024

        offset = 0
        while chunk := data[offset : offset + chunk_size]:
            if self._stop_event.is_set():
                self._stop_event.clear()
                return False

            self._stream.write(chunk)
            offset += chunk_size

        self._stop_event.clear()
        return True

    def _play_stimulus_sequence(self, tones: list[StimulusSequenceUnit]) -> bool:
        """Internal helper that applies volume overrides before each stimulus unit."""
        for tone in tones:
            if tone.master_volume is not None and tone.digital_volume is not None:
                self._theater.acontroller.set_master_volume(tone.master_volume)
                self._theater.acontroller.set_digital_volume(tone.digital_volume)

            if tone.stimulus is None:
                continue

            data = tone.stimulus.tobytes()
            chunk_size = 1024

            offset = 0
            while chunk := data[offset : offset + chunk_size]:
                if self._stop_event.is_set():
                    self._stop_event.clear()
                    return False

                self._stream.write(chunk)
                offset += chunk_size

        self._stop_event.clear()
        return True

    def play_file(self, path: str | Path) -> Future[bool]:
        """
        Play a mono 16-bit WAV file using the same PyAudio stream.

        Returns a Future[bool] that resolves to:
        - True  if playback finished normally
        - False if it was interrupted by stop() or an error
        """
        self._stop_event.clear()
        wav_path = Path(path)

        def _play_wav() -> bool:
            try:
                if not wav_path.exists():
                    print(f"[APlayer] WAV file not found: {wav_path}")
                    return False

                with wave.open(str(wav_path), "rb") as wf:
                    # Basic sanity checks – we still stream even if mismatch,
                    # but playback speed/pitch may differ if the sample rate is not SAMPLE_RATE.
                    channels = wf.getnchannels()
                    width = wf.getsampwidth()
                    rate = wf.getframerate()

                    if channels != 1 or width != 2:
                        print(
                            f"[APlayer] Warning: expected mono 16-bit WAV, "
                            f"got channels={channels}, width={width * 8} bits."
                        )
                    if rate != SAMPLE_RATE:
                        print(
                            f"[APlayer] Warning: expected sample rate {SAMPLE_RATE}, "
                            f"got {rate}. Audio will play at a different speed."
                        )

                    chunk_size = 1024
                    while True:
                        if self._stop_event.is_set():
                            self._stop_event.clear()
                            return False

                        data = wf.readframes(chunk_size)
                        if not data:
                            break

                        self._stream.write(data)

                self._stop_event.clear()
                return True

            except Exception as e:
                print(f"[APlayer] Error playing WAV file {wav_path}: {e}")
                self._stop_event.clear()
                return False

        return self._executor.submit(_play_wav)

    def play_stimulus(self, stimulus: NDArray[np.int16]) -> Future[bool]:
        """Play a single stimulus without adjusting system volume between tones."""
        self._stop_event.clear()
        return self._executor.submit(self._play_stimulus, stimulus)

    def play_stimulus_sequence(self, tones: list[StimulusSequenceUnit]) -> Future[bool]:
        """Play a sequence and update master/digital volume before each unit if provided."""
        self._stop_event.clear()
        return self._executor.submit(self._play_stimulus_sequence, tones)

    def stop(self) -> None:
        self._stop_event.set()

    def __del__(self) -> None:
        self._stream.close()
        self._player.terminate()
        self._executor.shutdown(wait=False)


if __name__ == "__main__":
    theater = Theater()

    player = APlayer(theater)

    freq_1 = ToneConfig(frequency=1000, duration=100)
    count = 1

    tone_s = player.generate_stimulus([freq_1], count)

    sequence_units = [
        StimulusSequenceUnit(frequency=2000, duration=100, interval=200),
        StimulusSequenceUnit(frequency=1000, duration=100, interval=200),
    ]
    sequence = player.generate_stimulus_sequence(sequence_units, duration=1201)

    player._play_stimulus_sequence([StimulusSequenceUnit(stimulus=tone_s)])
    player._play_stimulus_sequence(sequence)

    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(12, 6))

    normalized_tone = tone_s / np.iinfo(np.int16).max
    time_axis = np.linspace(0, len(tone_s) / SAMPLE_RATE * 1000, len(tone_s))
    axes[0].plot(time_axis, normalized_tone)
    axes[0].set_title(f"Single Stimulus - {freq_1.frequency}Hz, {freq_1.duration}ms")
    axes[0].set_xlim(0, freq_1.duration)
    axes[0].set_ylabel("Amplitude")
    axes[0].grid(True)

    stacked_sequence = np.concatenate(
        [unit.stimulus for unit in sequence if unit.stimulus is not None]
    )
    normalized_sequence = stacked_sequence / np.iinfo(np.int16).max
    sequence_time_axis = np.linspace(
        0, len(stacked_sequence) / SAMPLE_RATE * 1000, len(stacked_sequence)
    )
    axes[1].plot(sequence_time_axis, normalized_sequence)
    axes[1].set_title("Alternating Tone Blocks: 2000Hz ↔ 1000Hz")
    axes[1].set_xlabel("Time (ms)")
    axes[1].set_ylabel("Amplitude")
    axes[1].grid(True)

    block_edges: list[tuple[float, float, int | None]] = []
    cursor = 0.0
    for unit in sequence:
        if unit.stimulus is None:
            continue
        block_duration_ms = len(unit.stimulus) / SAMPLE_RATE * 1000
        block_edges.append((cursor, cursor + block_duration_ms, unit.frequency))
        cursor += block_duration_ms

    for start, end, freq in block_edges:
        axes[1].axvline(start, color="grey", linestyle="--", alpha=0.5)
        midpoint = (start + end) / 2
        label = f"{freq or 0}Hz"
        axes[1].annotate(
            label,
            xy=(midpoint, 0.8),
            xycoords=("data", "axes fraction"),
            ha="center",
            va="center",
            fontsize=10,
            bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"),
        )
    axes[1].axvline(cursor, color="grey", linestyle="--", alpha=0.5)
    axes[1].set_xlim(0, cursor)

    plt.tight_layout()
    plt.show()
