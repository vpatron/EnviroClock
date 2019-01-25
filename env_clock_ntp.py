from ntptime import settime
import network
import machine
from TM1637 import TM1637
import gc
import time
from si7021 import Si7021
from umqtt.simple import MQTTClient
from sys import exit
from os import listdir
import ujson

gc.collect()

with open('config.json') as f:
    cfg = ujson.load(f)
cfg_wifi = cfg['wifi']
cfg_gpio = cfg['gpio']
cfg_mqtt = cfg['mqtt']
cfg_time = cfg['time']

# Push button on GPIO0 stops the program
button = machine.Pin(0, machine.Pin.IN)


def mqtt_publish(temp_C, rh_Pct):
    mqtt_pub = MQTTClient(
        cfg_wifi['hostname'],
        cfg_mqtt['server'],
        user=cfg_mqtt['user'],
        password=cfg_mqtt['pwd'])
    mqtt_pub.connect()
    mqtt_pub.publish(cfg_mqtt['topic_temp'], str(temp_C).encode())
    mqtt_pub.publish(cfg_mqtt['topic_rh'], str(rh_Pct).encode())
    mqtt_pub.disconnect()


def do_connect():
    # Connect station to home wifi access point
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        sta_if.active(True)
        sta_if.config(dhcp_hostname=cfg_wifi['hostname'])
        sta_if.connect(cfg_wifi['ssid'], cfg_wifi['pwd'])
        while not sta_if.isconnected():
            pass
    print(sta_if.ifconfig()[0])
    ip_addr = sta_if.ifconfig()[0]

    # Turn off internal access point
    ap_if = network.WLAN(network.AP_IF)
    ap_if.active(False)
    return ip_addr


led = TM1637(cfg_gpio['led_scl'], cfg_gpio['led_sda'])
led.set_text(' 1P ')
led.set_brightness(4)
time.sleep(1.5)

# Connect to WiFi and show IP address
ip_addr = do_connect()
ip_node = ip_addr.split('.')[3]
led.set_text('    ')
led.set_text(' {:>4}'.format('.' + ip_node))
time.sleep(2)

# Set system time from time server pool.ntp.org
# Do this once a day to reduce time server loading.
# Call machine.RTC().datetime() rest of the time.
#settime()

# Temp and RH sensor
sns = Si7021(scl=cfg_gpio['sns_scl'], sda=cfg_gpio['sns_sda'])


def show_time(hr, mn):
    # Adjust for time zone offset
    hr += cfg_time['tz_offset']
    if hr < 0:
        hr += 24
    hr = hr % 24

    # Convert 24 hour to 12 hour time
    if hr == 0:
        hr = 12
    elif hr > 12:
        hr -= 12

    # Convert to time format with decimal point as colon
    tme_txt = '{:>2}.{:>02}'.format(hr, mn)
    led.set_text(tme_txt)


def show_temp():
    temp_c = sns.readTemp()
    temp_f = temp_c * 9.0 / 5 + 32
    if temp_f <= 99.9:
        txt = '{:>4.1f}F'.format(temp_f)
    else:
        txt = '{:>4.0f}F'.format(temp_f)
    led.set_text(txt)
    return temp_c


def show_rh():
    rh = sns.readRH()
    if rh > 99:
        rh = 99
    txt = 'rh{:>2.0f}'.format(rh)
    led.set_text(txt)
    return rh


def update_time(time_epoch):
    """Call this when we have new epoch time data from MQTT server so we can update
    our internal RTC."""
    # Convert to local time format and then set RTC to that. RTC has no time zone
    # support. Time zone is handled at display formatting.
    tm = time.localtime(time_epoch)
    tm = tm[0:3] + (0,) + tm[3:6] + (0,)
    machine.RTC().datetime(tm)


# Preloop init
old_mn = -1
old_sec = -1
next_mqtt_pub = 0
next_get_time = 0
gc.collect()
temp = None
rh = None

# Loop to update time display
while True:
    if button.value() == 0:
        break
    tme = machine.RTC().datetime()
    sec = tme[6]
    mn = tme[5]
    hr = tme[4]

    # Fall through only once per second
    time.sleep(0.2)
    if sec == old_sec:
        continue
    old_sec = sec
    gc.collect()

    # Update RTC from network time every so often
    # ESP8266 RTC drifts very badly
    next_get_time -= 1
    if next_get_time <= 0:
        try:
            settime()
        except:
            next_get_time = 60
            print('Warning: get NTP time failed. Retrying in one minute.')
        else:
            next_get_time = cfg_time['update_rate']

    # Cycle through Time, Temperature, RH
    # 12 second cycle
    disp_count = time.time() % 12
    if disp_count == 0:
        show_time(hr, mn)
    elif disp_count == 8:
        temp = round(show_temp(), 2)
    elif disp_count == 10:
        rh = round(show_rh(), 2)

    # Check if we need to publish MQTT temperature and humidity
    # Publish it after 30 second mark. Try not to collide with MQTT time subscribed message
    # at 00 seconds. Sometimes misses it if pub same time as sub message comes in.
    next_mqtt_pub -= 1
    if next_mqtt_pub <= 0 and sec > 30 and temp != None and rh != None:
        print('publishing temp={} rh={}'.format(temp, rh))
        try:
            mqtt_publish(temp, rh)
        except OSError:
            next_mqtt_pub = 30
            print('Warning: MQTT publish failed. Retrying in 30 seconds.')
        else:
            next_mqtt_pub = cfg_mqtt['rate']


# Exit program

# Wait until button is released before updating display
# Button also uses same LED IO pins
while button.value() == 0:
    time.sleep(0.1)
time.sleep(0.1)
led.set_text('5toP')
print('Stopped')
