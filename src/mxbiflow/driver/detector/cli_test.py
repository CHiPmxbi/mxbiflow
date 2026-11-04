from cyclopts import App
from rich.prompt import FloatPrompt, IntPrompt, Prompt

app = App(version_flags=[], result_action="return_value")


def prompt_detector_config() -> tuple[str, int, int, float, float]:
    port = Prompt.ask("RFID serial port", default="/dev/ttyUSB0")
    if not port.strip():
        raise SystemExit("port cannot be empty")

    baudrate = IntPrompt.ask("RFID baudrate", default=9600)
    if baudrate <= 0:
        raise SystemExit("baudrate must be > 0")

    pin = IntPrompt.ask("Beam-break GPIO pin", default=17)
    if pin < 0:
        raise SystemExit("pin must be >= 0")

    poll_interval = FloatPrompt.ask("Detector poll interval (seconds)", default=0.05)
    if poll_interval <= 0:
        raise SystemExit("poll_interval must be > 0")

    rfid_timeout = FloatPrompt.ask("RFID timeout window (seconds)", default=10.0)
    if rfid_timeout <= 0:
        raise SystemExit("rfid_timeout must be > 0")

    return port, baudrate, pin, poll_interval, rfid_timeout


@app.default
def run() -> None:
    from time import sleep

    from ..peripheral.beam_break_sensor.rpi_ir_break_beam_sensor import (
        RPIIRBreakBeamSensor,
    )
    from ..peripheral.rfid.dorset_lid665v42 import DorsetLID665v42
    from .detector import DetectorEvent
    from .fusion_continuous_detector import FusionContinuousDetector

    port, baudrate, pin, poll_interval, rfid_timeout = prompt_detector_config()

    rfid_reader = DorsetLID665v42(port=port, baudrate=baudrate)
    beam_break_sensor = RPIIRBreakBeamSensor(pin=pin)

    detector = FusionContinuousDetector(
        rfid_reader,
        beam_break_sensor,
        poll_interval=poll_interval,
        rfid_timeout=rfid_timeout,
    )

    detector.register_event(DetectorEvent.ANIMAL_ENTERED, print_animal_entered)
    detector.register_event(DetectorEvent.ANIMAL_LEFT, print_animal_exited)

    detector.begin()

    print("Listening detector events... (Ctrl+C to stop)")
    try:
        while True:
            sleep(1.0)
    except KeyboardInterrupt:
        print("Exiting.")
    finally:
        detector.quit()


def print_animal_entered(result) -> None:
    print(f"[ENTER] animal_id={result.animal_id}, error={result.error}")


def print_animal_exited(result) -> None:
    print(f"[LEAVE] animal_id={result.animal_id}, error={result.error}")


if __name__ == "__main__":
    app()
