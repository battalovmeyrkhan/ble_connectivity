# ble_pibody.py
import bluetooth
import time
from micropython import const

# =========================================================
# IRQ events
# =========================================================
_IRQ_CENTRAL_CONNECT              = const(1)
_IRQ_CENTRAL_DISCONNECT           = const(2)

_IRQ_SCAN_RESULT                  = const(5)
_IRQ_SCAN_DONE                    = const(6)

_IRQ_PERIPHERAL_CONNECT           = const(7)
_IRQ_PERIPHERAL_DISCONNECT        = const(8)

_IRQ_GATTC_SERVICE_RESULT         = const(9)
_IRQ_GATTC_SERVICE_DONE           = const(10)
_IRQ_GATTC_CHARACTERISTIC_RESULT  = const(11)
_IRQ_GATTC_CHARACTERISTIC_DONE    = const(12)
_IRQ_GATTC_READ_RESULT            = const(15)
_IRQ_GATTC_READ_DONE              = const(16)

# =========================================================
# Flags
# =========================================================
_FLAG_READ = const(0x0002)
_FLAG_NOTIFY = const(0x0010)

# =========================================================
# Default UUIDs
# =========================================================
_DEFAULT_SERVICE_UUID = bluetooth.UUID("12345678-1234-5678-1234-56789abcdef0")
_DEFAULT_CHAR_UUID    = bluetooth.UUID("abcd1234-5678-1234-5678-1234567890ab")

# =========================================================
# Helpers
# =========================================================
def _decode_name(adv_data):
    i = 0
    n = len(adv_data)

    while i + 1 < n:
        length = adv_data[i]
        if length == 0:
            break

        adv_type = adv_data[i + 1]
        if adv_type == 0x09:
            try:
                return adv_data[i + 2:i + 1 + length].decode("utf-8")
            except:
                return None

        i += 1 + length

    return None


def _advertising_payload(name):
    name_bytes = name.encode("utf-8")
    return bytes((len(name_bytes) + 1, 0x09)) + name_bytes


# =========================================================
# Peripheral
# =========================================================
class peripheral:
    def __init__(self, name="PICO_B", service_uuid=None, char_uuid=None, initial_value="0"):
        self.name = name
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq)

        self.service_uuid = bluetooth.UUID(service_uuid) if service_uuid else _DEFAULT_SERVICE_UUID
        self.char_uuid = bluetooth.UUID(char_uuid) if char_uuid else _DEFAULT_CHAR_UUID

        self._connections = set()
        self._data_func = None

        self._service = (
            self.service_uuid,
            (
                (self.char_uuid, _FLAG_READ | _FLAG_NOTIFY),
            ),
        )

        ((self._value_handle,),) = self.ble.gatts_register_services((self._service,))
        self.set_value(initial_value)

    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, addr_type, addr = data
            self._connections.add(conn_handle)
            print("Central connected:", conn_handle)

        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, addr_type, addr = data
            if conn_handle in self._connections:
                self._connections.remove(conn_handle)
            print("Central disconnected:", conn_handle)
            self.advertise()

    def advertise(self, interval_us=500000):
        payload = _advertising_payload(self.name)
        self.ble.gap_advertise(interval_us, adv_data=payload)
        print("Advertising as:", self.name)

    def set_value(self, value):
        if isinstance(value, str):
            value = value.encode("utf-8")
        self.ble.gatts_write(self._value_handle, value)

    def set_data(self, func):
        """
        Назначает функцию, которая будет возвращать данные для отправки.
        """
        self._data_func = func
        return self

    def data(self, func):
        """
        Декоратор:
        @p.data
        def send():
            return "hello"
        """
        self._data_func = func
        return func

    def notify_all(self):
        for conn_handle in self._connections:
            try:
                self.ble.gatts_notify(conn_handle, self._value_handle)
            except Exception as e:
                print("Notify error:", e)

    def start(self, every_ms=1000, notify=False):
        self.advertise()

        while True:
            if self._data_func is not None:
                try:
                    value = self._data_func()
                    self.set_value(value)

                    if notify:
                        self.notify_all()

                except Exception as e:
                    print("Peripheral update error:", e)

            time.sleep_ms(every_ms)


# =========================================================
# Central
# =========================================================
class central:
    def __init__(self, target_names, service_uuid=None, char_uuid=None):
        self.target_names = target_names
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq)

        self.service_uuid = bluetooth.UUID(service_uuid) if service_uuid else _DEFAULT_SERVICE_UUID
        self.char_uuid = bluetooth.UUID(char_uuid) if char_uuid else _DEFAULT_CHAR_UUID

        self._on_read = None
        self._found = {}
        self._current_target = None
        self._conn_handle = None
        self._start_handle = None
        self._end_handle = None
        self._value_handle = None
        self._busy = False

    def on_read(self, func):
        self._on_read = func
        return func

    def _clear_connection_state(self):
        self._conn_handle = None
        self._start_handle = None
        self._end_handle = None
        self._value_handle = None
        self._busy = False

    def _irq(self, event, data):
        if event == _IRQ_SCAN_RESULT:
            addr_type, addr, adv_type, rssi, adv_data = data
            name = _decode_name(adv_data)

            if name in self.target_names and name not in self._found:
                self._found[name] = (addr_type, bytes(addr))
                print("Found", name, "RSSI:", rssi)

        elif event == _IRQ_SCAN_DONE:
            print("Scan done")

        elif event == _IRQ_PERIPHERAL_CONNECT:
            conn_handle, addr_type, addr = data
            self._conn_handle = conn_handle
            print("Connected to", self._current_target, "conn_handle =", conn_handle)
            self.ble.gattc_discover_services(conn_handle)

        elif event == _IRQ_PERIPHERAL_DISCONNECT:
            conn_handle, addr_type, addr = data
            print("Disconnected from", self._current_target)
            self._clear_connection_state()

        elif event == _IRQ_GATTC_SERVICE_RESULT:
            conn_handle, start_handle, end_handle, uuid = data
            if uuid == self.service_uuid:
                self._start_handle = start_handle
                self._end_handle = end_handle
                print("Service found:", start_handle, end_handle)

        elif event == _IRQ_GATTC_SERVICE_DONE:
            if self._start_handle is not None and self._end_handle is not None:
                self.ble.gattc_discover_characteristics(
                    self._conn_handle,
                    self._start_handle,
                    self._end_handle
                )
            else:
                try:
                    self.ble.gap_disconnect(self._conn_handle)
                except:
                    self._clear_connection_state()

        elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
            conn_handle, def_handle, value_handle, properties, uuid = data
            if uuid == self.char_uuid:
                self._value_handle = value_handle
                print("Characteristic found, value_handle =", value_handle)

        elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
            if self._value_handle is not None:
                self.ble.gattc_read(self._conn_handle, self._value_handle)
            else:
                try:
                    self.ble.gap_disconnect(self._conn_handle)
                except:
                    self._clear_connection_state()

        elif event == _IRQ_GATTC_READ_RESULT:
            conn_handle, value_handle, char_data = data
            try:
                value = bytes(char_data).decode("utf-8")
            except:
                value = str(bytes(char_data))

            print("READ from", self._current_target, "=>", value)

            if self._on_read:
                try:
                    self._on_read(self._current_target, value)
                except Exception as e:
                    print("Central callback error:", e)

        elif event == _IRQ_GATTC_READ_DONE:
            if self._conn_handle is not None:
                try:
                    self.ble.gap_disconnect(self._conn_handle)
                except:
                    self._clear_connection_state()

    def scan(self, duration_ms=3000):
        self._found = {}
        print("Scanning...")
        self.ble.gap_scan(duration_ms, 30000, 30000)
        time.sleep_ms(duration_ms + 300)
        return self._found

    def connect_and_read(self, name, timeout_ms=6000):
        if name not in self._found:
            print(name, "not found")
            return False

        addr_type, addr = self._found[name]
        self._current_target = name
        self._busy = True

        print("Connecting to", name)

        try:
            self.ble.gap_connect(addr_type, addr)
        except Exception as e:
            print("Connect error:", e)
            self._clear_connection_state()
            return False

        start = time.ticks_ms()

        while self._busy:
            if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
                print("Timeout with", name)
                try:
                    if self._conn_handle is not None:
                        self.ble.gap_disconnect(self._conn_handle)
                except:
                    pass
                self._clear_connection_state()
                return False

            time.sleep_ms(100)

        return True

    def start(self, scan_time_ms=3000, pause_ms=2000):
        while True:
            self.scan(scan_time_ms)

            for name in self.target_names:
                self.connect_and_read(name)
                time.sleep_ms(300)

            time.sleep_ms(pause_ms)
