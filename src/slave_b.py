import bluetooth
import struct
import time
from micropython import const

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)

_FLAG_READ = const(0x0002)
_FLAG_NOTIFY = const(0x0010)

SERVICE_UUID = bluetooth.UUID("12345678-1234-5678-1234-56789abcdef0")
CHAR_UUID    = bluetooth.UUID("12345678-1234-5678-1234-56789abcdef1")


class BLESlave:
    def __init__(self, device_name, prefix, start_value=0):
        self.device_name = device_name
        self.prefix = prefix
        self.value = start_value
        self.connections = set()

        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq)

        service = (
            SERVICE_UUID,
            (
                (CHAR_UUID, _FLAG_READ | _FLAG_NOTIFY),
            ),
        )

        ((self.char_handle,),) = self.ble.gatts_register_services((service,))
        self.advertise()

    def _advertising_payload(self, name=None):
        payload = bytearray()

        def _append(adv_type, value):
            payload.extend(struct.pack("BB", len(value) + 1, adv_type))
            payload.extend(value)

        _append(0x01, b"\x06")  # flags

        if name:
            _append(0x09, name.encode())  # complete local name

        return payload

    def advertise(self):
        payload = self._advertising_payload(name=self.device_name)
        self.ble.gap_advertise(100, adv_data=payload)
        print("Advertising as", self.device_name)

    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, addr_type, addr = data
            print("Central connected:", conn_handle)
            self.connections.add(conn_handle)

        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, addr_type, addr = data
            print("Central disconnected:", conn_handle)
            if conn_handle in self.connections:
                self.connections.remove(conn_handle)
            self.advertise()

    def update_value(self):
        self.value += 1
        msg = "{}:{}".format(self.prefix, self.value)
        self.ble.gatts_write(self.char_handle, msg)
        return msg

    def notify_all(self, msg):
        for conn_handle in self.connections:
            try:
                self.ble.gatts_notify(conn_handle, self.char_handle)
            except Exception as e:
                print("Notify error:", e)

    def run(self, delay=2):
        while True:
            msg = self.update_value()
            self.notify_all(msg)
            print("Sent:", msg)
            time.sleep(delay)


slave_b = BLESlave(device_name="PICO_B", prefix="B", start_value=100)
slave_b.run()
