"""The audio player: sounds of any format, played together on one output."""

import io
import unittest
from typing import Any
from unittest.mock import Mock, patch

import numpy as np
import soundfile
from numpy.typing import NDArray

from mxbiflow.assets import CLICKER_PATH
from mxbiflow.driver.audioplayer import (
    AudioFormat,
    AudioPlayer,
    Sound,
    convert,
    read_sound,
)
from mxbiflow.driver.audioplayer.mixer import Mixer
from mxbiflow.task import TaskResult, TaskStatus

MONO = AudioFormat(sample_rate_hz=1000, channels=1)
STEREO = AudioFormat(sample_rate_hz=1000, channels=2)


def sound(*values: float, sample_rate_hz: int = 1000) -> Sound:
    """A sound of one channel with these samples."""
    samples = np.array(values, dtype=np.float32).reshape(-1, 1)
    return Sound(samples=samples, sample_rate_hz=sample_rate_hz)


def block(mixer: Mixer, frames: int) -> list[float]:
    """The first channel of the mixer's next block."""
    out = np.empty((frames, mixer.format.channels), dtype=np.float32)
    mixer.render(out)
    return [round(float(x), 3) for x in out[:, 0]]


class SoundTests(unittest.TestCase):
    def test_a_file_of_any_sample_type_is_read_as_samples(self) -> None:
        for subtype in ("PCM_16", "PCM_24", "FLOAT"):
            with self.subTest(subtype):
                file = io.BytesIO()
                data = np.array([[0.5, -0.5], [0.25, 0.0]], dtype=np.float32)
                soundfile.write(file, data, 97656, format="WAV", subtype=subtype)
                file.seek(0)

                read = read_sound(file)

                self.assertEqual(
                    read.format, AudioFormat(sample_rate_hz=97656, channels=2)
                )
                np.testing.assert_allclose(read.samples, data, atol=1e-4)

    def test_a_sound_is_resampled_to_the_outputs_rate(self) -> None:
        # A second of a 1 kHz tone at the twitters' sample rate.
        t = np.arange(97656) / 97656
        tone = np.sin(2 * np.pi * 1000 * t).astype(np.float32).reshape(-1, 1)

        converted = convert(
            Sound(samples=tone, sample_rate_hz=97656),
            to=AudioFormat(sample_rate_hz=96000, channels=1),
        )

        self.assertEqual(converted.frames, 96000)
        self.assertEqual(converted.duration_ms, 1000)
        # Still the same tone: it crosses zero 2000 times.
        signs = np.signbit(converted.samples[:, 0])
        self.assertAlmostEqual(
            int(np.count_nonzero(signs[1:] != signs[:-1])), 2000, delta=2
        )

    def test_one_channel_goes_to_every_channel_and_two_are_averaged(self) -> None:
        up = convert(sound(0.5, -0.25), to=STEREO)
        self.assertEqual(up.samples.tolist(), [[0.5, 0.5], [-0.25, -0.25]])

        down = convert(up, to=MONO)
        self.assertEqual(down.samples.tolist(), [[0.5], [-0.25]])

    def test_another_change_of_channels_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "2 channels cannot be played on 6"):
            convert(convert(sound(0.5), to=STEREO), to=AudioFormat(1000, 6))

    def test_samples_of_the_wrong_shape_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "frames by channels"):
            Sound(samples=np.zeros(4, dtype=np.float32), sample_rate_hz=1000)


class MixerTests(unittest.TestCase):
    def test_sounds_started_at_different_times_play_together(self) -> None:
        mixer = Mixer(format=MONO)
        long = mixer.add(sound=sound(0.1, 0.1, 0.1, 0.1), gain=1.0)
        self.assertEqual(block(mixer, 2), [0.1, 0.1])

        short = mixer.add(sound=sound(0.5), gain=0.5)
        self.assertEqual(block(mixer, 2), [0.35, 0.1])
        self.assertEqual(block(mixer, 2), [0.0, 0.0])

        # Their tasks end on the game loop's thread, not the audio thread's.
        self.assertFalse(long.done or short.done)
        mixer.update()
        self.assertEqual(long.result, TaskResult(TaskStatus.FINISHED))
        self.assertEqual(short.result, TaskResult(TaskStatus.FINISHED))

    def test_a_cancelled_sound_stops_with_the_next_block(self) -> None:
        mixer = Mixer(format=MONO)
        stays = mixer.add(sound=sound(0.1, 0.1, 0.1, 0.1), gain=1.0)
        goes = mixer.add(sound=sound(0.2, 0.2, 0.2, 0.2), gain=1.0)
        seen: list[TaskStatus] = []
        goes.on_done(lambda result: seen.append(result.status))
        block(mixer, 2)

        goes.cancel()

        self.assertEqual(block(mixer, 2), [0.1, 0.1])
        mixer.update()
        self.assertEqual(seen, [TaskStatus.CANCELLED])
        self.assertEqual(stays.result, TaskResult(TaskStatus.FINISHED))

    def test_a_sum_that_is_too_loud_is_clipped_and_said(self) -> None:
        mixer = Mixer(format=MONO)
        mixer.add(sound=sound(0.8), gain=1.0)
        mixer.add(sound=sound(0.7), gain=1.0)

        self.assertEqual(block(mixer, 1), [1.0])
        with self.assertLogs("mxbiflow.driver.audioplayer.mixer", "WARNING") as logs:
            mixer.update()
        self.assertIn("1 blocks clipped", logs.output[0])

    def test_a_sound_in_another_format_is_refused(self) -> None:
        mixer = Mixer(format=STEREO)
        with self.assertRaisesRegex(ValueError, "convert it before playing"):
            mixer.add(sound=sound(0.1), gain=1.0)


class AudioPlayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stream = Mock()
        patcher = patch(
            "mxbiflow.driver.audioplayer.audioplayer.sounddevice.OutputStream",
            return_value=self.stream,
        )
        self.opened = patcher.start()
        self.addCleanup(patcher.stop)

    def render(self, frames: int) -> NDArray[np.float32]:
        """What the output would play next."""
        callback: Any = self.opened.call_args.kwargs["callback"]
        out = np.empty((frames, 2), dtype=np.float32)
        callback(out, frames, None, None)
        return out

    def test_files_of_different_formats_play_together_on_one_stream(self) -> None:
        player = AudioPlayer(sample_rate_hz=96000)
        clicker = player.load(CLICKER_PATH)
        twitter = player.prepare(sound(0.25, 0.25, sample_rate_hz=97656))

        first = player.play(clicker)
        second = player.play(twitter, gain=0.5)

        self.opened.assert_called_once()
        self.assertEqual(self.opened.call_args.kwargs["samplerate"], 96000)
        self.assertEqual(clicker.format, AudioFormat(sample_rate_hz=96000, channels=2))
        # The clicker's half second at the output's rate.
        self.assertEqual(clicker.frames, 48000)
        self.render(48000)
        player.update()
        self.assertTrue(first.done and second.done)

    def test_without_a_sample_rate_the_devices_own_is_used(self) -> None:
        with patch(
            "mxbiflow.driver.audioplayer.audioplayer.sounddevice.query_devices",
            return_value={"default_samplerate": 48000.0},
        ):
            player = AudioPlayer()
            self.assertEqual(
                player.format, AudioFormat(sample_rate_hz=48000, channels=2)
            )

    def test_a_format_the_device_does_not_take_fails_when_opened(self) -> None:
        self.opened.side_effect = RuntimeError("Invalid sample rate")
        with self.assertRaisesRegex(RuntimeError, "Invalid sample rate"):
            AudioPlayer(sample_rate_hz=12345).open()

    def test_cancelling_all_ends_every_sound(self) -> None:
        player = AudioPlayer(sample_rate_hz=1000)
        tasks = [player.play(player.prepare(sound(0.1, 0.1, 0.1))) for _ in range(2)]

        player.cancel_all()
        self.render(1)
        player.update()

        self.assertEqual(
            [task.result for task in tasks], [TaskResult(TaskStatus.CANCELLED)] * 2
        )

    def test_closing_ends_the_sounds_and_the_stream(self) -> None:
        player = AudioPlayer(sample_rate_hz=1000)
        task = player.play(player.prepare(sound(0.1, 0.1)))

        player.close()

        self.stream.close.assert_called_once()
        self.assertEqual(task.result, TaskResult(TaskStatus.CANCELLED))


if __name__ == "__main__":
    unittest.main()
