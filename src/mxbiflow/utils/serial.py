from serial import SerialBase
from serial.tools import list_ports


def get_baudrates():
    return [(str(baudrate), baudrate) for baudrate in SerialBase.BAUDRATES]


def get_all_ports():
    return [port.device for port in list_ports.comports() if port.device is not None]
