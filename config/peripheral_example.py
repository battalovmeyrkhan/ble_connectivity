from ble_pibody import peripheral #Импорт библиотеки

p = peripheral("PICO_C") #

from ble_pibody import peripheral
from machine import Pin
import dht

# создаем объект датчика
sensor = dht.DHT22(Pin(15))

p = peripheral("PICO_C") # название периферии

@p.data #p.set.data (упрощенно)
def send(): # создаем то, что будем отправлять
    try:
        sensor.measure()  # обновляем данные
        temp = sensor.temperature()
        hum = sensor.humidity()

        return "T:{};H:{}".format(temp, hum) # отправляем данные мастеру и формат

    except Exception as e:
        return "ERROR"

p.start(every_ms=2000) # частота отправления


==================================================

from ble_pibody import central # импорт библиотеки

c = central(["PICO_B", "PICO_C"]) # берет информацию с каких периферий

@c.on_read # чтение
def handle(device, value):
    print(device, "=>", value)

c.start(scan_time_ms=3000, pause_ms=2000) #скан раз в 3 секунды, пауза 2 секунды
