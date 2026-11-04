from time import sleep

from cyclopts import App
from rich.prompt import Confirm, FloatPrompt, IntPrompt

app = App(version_flags=[], result_action="return_value")


def prompt_sensor_config() -> tuple[int, float, bool]:
    pin = IntPrompt.ask("GPIO pin", default=17)
    if pin < 0:
        raise SystemExit("pin must be >= 0")

    debounce_time = FloatPrompt.ask("Debounce time (seconds)", default=0.05)
    if debounce_time < 0:
        raise SystemExit("debounce_time must be >= 0")

    normally_open = Confirm.ask("Normally open?", default=True)
    return pin, debounce_time, normally_open


@app.default
def run() -> None:
    from .rpi_ir_break_beam_sensor import RPIIRBreakBeamSensor

    pin, debounce_time, normally_open = prompt_sensor_config()
    sensor = RPIIRBreakBeamSensor(
        pin=pin,
        debounce_time=debounce_time,
        normally_open=normally_open,
    )

    try:
        while True:
            print(sensor.read())
            sleep(0.1)
    except KeyboardInterrupt:
        print("Exiting.")


if __name__ == "__main__":
    app()
