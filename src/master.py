import bluetooth
import time
from micropython import const

_IRQ_SCAN_RESULT = const(5)
_IRQ_SCAN_DONE = const(6)
_IRQ_PERIPHERAL_CONNECT = const(7)
_IRQ_PERIPHERAL_DISCONNECT = const(8)
_IRQ_GATTC_SERVICE_RESULT = const(9)
_IRQ_GATTC_SERVICE_DONE = const(10)
_IRQ_GATTC_CHARACTERISTIC_RESULT = const(11)
_IRQ_GATTC_CHARACTERISTIC_DONE = const(12)
_IRQ_GATTC_READ_RESULT = const(15)
_IRQ_GATTC_READ_DONE = const(16)

SERVICE_UUID = bluetooth.UUID("12345678-1234-5678-1234-56789abcdef0")
CHAR_UUID    = bluetooth.UUID("12345678-1234-5678-1234-56789abcdef1")


class BLEMaster:
    def __init__(self, targets):
        self.targets = targets
        self.current_target_index = 0
        self.current_target_name = self.targets[self.current_target_index]

        self.found_addr_type = None
        self.found_addr = None

        self.conn_handle = None
        self.start_handle = None
        self.end_handle = None
        self.value_handle = None

        self.state = "idle"

        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq)

    def decode_name(self, adv_data):
        i = 0
        while i + 1 < len(adv_data):
            length = adv_data[i]
            if length == 0:
                break
            adv_type = adv_data[i + 1]
            if adv_type == 0x09:
                try:
                    return adv_data[i + 2:i + 1 + length].decode()
                except:
                    return None
            i += 1 + length
        return None

    def reset_connection_data(self):
        self.found_addr_type = None
        self.found_addr = None
        self.conn_handle = None
        self.start_handle = None
        self.end_handle = None
        self.value_handle = None

    def next_target(self):
        self.current_target_index = (self.current_target_index + 1) % len(self.targets)
        self.current_target_name = self.targets[self.current_target_index]

    def start_scan(self):
        self.reset_connection_data()
        self.current_target_name = self.targets[self.current_target_index]
        self.state = "scanning"
        print("\nScanning for", self.current_target_name)
        self.ble.gap_scan(5000, 30000, 30000)

    def handle_scan_result(self, data):
        addr_type, addr, adv_type, rssi, adv_data = data
        name = self.decode_name(bytes(adv_data))

        if name == self.current_target_name:
            print("Found", name, "RSSI:", rssi)
            self.found_addr_type = addr_type
            self.found_addr = bytes(addr)
            self.ble.gap_scan(None)

    def handle_scan_done(self):
        if self.state != "scanning":
            return

        if self.found_addr is not None:
            print("Connecting to", self.current_target_name)
            self.state = "connecting"
            try:
                self.ble.gap_connect(self.found_addr_type, self.found_addr)
            except Exception as e:
                print("Connect error:", e)
                self.next_target()
                time.sleep_ms(500)
                self.start_scan()
        else:
            print(self.current_target_name, "not found")
            self.next_target()
            time.sleep_ms(500)
            self.start_scan()

    def handle_connect(self, data):
        conn_handle, addr_type, addr = data
        self.conn_handle = conn_handle
        print("Connected to", self.current_target_name)
        self.state = "discover_service"

        try:
            self.ble.gattc_discover_services(self.conn_handle)
        except Exception as e:
            print("Service discovery error:", e)
            self.disconnect()

    def handle_service_result(self, data):
        conn_handle, start, end, uuid = data
        if uuid == SERVICE_UUID:
            self.start_handle = start
            self.end_handle = end

    def handle_service_done(self):
        if self.start_handle is not None and self.end_handle is not None:
            self.state = "discover_char"
            try:
                self.ble.gattc_discover_characteristics(
                    self.conn_handle,
                    self.start_handle,
                    self.end_handle
                )
            except Exception as e:
                print("Characteristic discovery error:", e)
                self.disconnect()
        else:
            print("Service not found on", self.current_target_name)
            self.disconnect()

    def handle_characteristic_result(self, data):
        conn_handle, def_handle, val_handle, properties, uuid = data
        if uuid == CHAR_UUID:
            self.value_handle = val_handle

    def handle_characteristic_done(self):
        if self.value_handle is not None:
            self.state = "reading"
            try:
                self.ble.gattc_read(self.conn_handle, self.value_handle)
            except Exception as e:
                print("Read start error:", e)
                self.disconnect()
        else:
            print("Characteristic not found on", self.current_target_name)
            self.disconnect()

    def handle_read_result(self, data):
        conn_handle, value_handle, char_data = data
        try:
            msg = bytes(char_data).decode()
        except:
            msg = bytes(char_data)
        print("Value from", self.current_target_name, "=>", msg)

    def handle_read_done(self):
        self.disconnect()

    def handle_disconnect(self):
        print("Disconnected from", self.current_target_name)
        self.state = "idle"
        time.sleep_ms(700)
        self.next_target()
        self.start_scan()

    def disconnect(self):
        try:
            self.ble.gap_disconnect(self.conn_handle)
        except Exception as e:
            print("Disconnect error:", e)

    def _irq(self, event, data):
        if event == _IRQ_SCAN_RESULT:
            self.handle_scan_result(data)

        elif event == _IRQ_SCAN_DONE:
            self.handle_scan_done()

        elif event == _IRQ_PERIPHERAL_CONNECT:
            self.handle_connect(data)

        elif event == _IRQ_GATTC_SERVICE_RESULT:
            self.handle_service_result(data)

        elif event == _IRQ_GATTC_SERVICE_DONE:
            self.handle_service_done()

        elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
            self.handle_characteristic_result(data)

        elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
            self.handle_characteristic_done()

        elif event == _IRQ_GATTC_READ_RESULT:
            self.handle_read_result(data)

        elif event == _IRQ_GATTC_READ_DONE:
            self.handle_read_done()

        elif event == _IRQ_PERIPHERAL_DISCONNECT:
            self.handle_disconnect()

    def run(self):
        self.start_scan()
        while True:
            time.sleep(1)


master = BLEMaster(targets=["PICO_B", "PICO_C"])
master.run()
