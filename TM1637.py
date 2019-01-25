#!/usr/bin/env python

from machine import Pin
import time

class TM1637:
    # Bit Position vs Segment Lit
    #
    #              +--a--+
    #              |     |
    #  Bit Pos.    f     b
    #  76543210    |     |
    #  --------    +--g--+
    #  *gfedcba    |     |
    #              e     c
    #              |     |
    #              +--d--+ *
    
    FONT = {
        '0': 0b00111111,
        '1': 0b00000110,
        '2': 0b01011011,
        '3': 0b01001111,
        '4': 0b01100110,
        '5': 0b01101101,
        '6': 0b01111101,
        '7': 0b00000111,
        '8': 0b01111111,
        '9': 0b01101111,
        'A': 0b01110111,
        'b': 0b01111100,
        'C': 0b00111001,
        'c': 0b01011000,
        'D': 0b01011110,
        'd': 0b01011110,
        'E': 0b01111001,
        'F': 0b01110001,
        ' ': 0b00000000,
        'H': 0b01110110,
        'h': 0b01110100,
        'I': 0b00110000,
        'i': 0b00010000,
        'J': 0b00011110,
        'L': 0b00111000,
        'l': 0b00110000,
        'n': 0b01010100,
        'o': 0b01011100,
        'P': 0b01110011,
        'r': 0b01010000,
        't': 0b01110000,
        'u': 0b00011100,
        'Y': 0b01101110,
        '-': 0b01000000,
        '=': 0b01001000,
        '.': 0b10000000
    }
    UNBLANK    = 0b10001111     # Max brightness
    BLANK      = 0b10000000
    ADDR_C0H   = 0b11000000     # Address of left-most character
    BRIGHTNESS = 0b10001000     # Lowest brightness setting
    AUTO_INCR  = 0b01000000     # Increments digit position as data is sent
    N_DIGITS = 4
    
    def start_cond(self):
        """From idle (clk=dio=1) go to start (clk=dio=0)"""
        self.dio.value(0)
        time.sleep_us(300)
        self.clk.value(0)
        time.sleep_us(300)
        
    def stop_cond(self):
        """After transaction idle (clk=dio=0) go to start (clk=dio=1)"""
        self.clk.value(1)
        time.sleep_us(300)
        self.dio.value(1)
        time.sleep_us(300)
        
    def get_ack(self):
        """After command or data, get the ACK bit. Previous command or
        data should leave clk=1. After this, clk=dio=0."""
        #self.dio = Pin(self.gpio_dio, Pin.IN)
        time.sleep_us(300)
        ack = self.dio.value()
        self.clk.value(1)
        time.sleep_us(600)
        #self.dio = Pin(self.gpio_dio, Pin.OUT, value=0)
        self.clk.value(0)
        time.sleep_us(300)
        return ack

    def send_byte(self, data, start=False, stop=False):
        #print(hex(data)) #debug
        if start:
            self.start_cond()
        mask = 1
        for i in range(8):
            time.sleep_us(200)
            if data & mask:
                self.dio.value(1)
            else:
                self.dio.value(0)
            mask <<= 1
            time.sleep_us(100)
            self.clk.value(1)
            time.sleep_us(300)
            self.clk.value(0)

        ack = self.get_ack()
        if stop:
            self.stop_cond()
        time.sleep_us(300)
        return ack

    def __init__(self, gpio_clk, gpio_dio):
        self.gpio_dio = gpio_dio
        self.gpio_clk = gpio_clk
        self.clk = Pin(gpio_clk, Pin.OPEN_DRAIN, value=1)
        self.dio = Pin(gpio_dio, Pin.OPEN_DRAIN, value=1)
        self.send_byte(self.UNBLANK, start=True, stop=True)
        self.send_byte(self.AUTO_INCR, start=True, stop=True)
        time.sleep_ms(10)
           
    def set_brightness(self, level):
        """Warning: TM1637 seems to have a bug. Repeated brightness
        changes seem to screw up the display RAM values."""
        if level <= 0:
            self.send_byte(self.BLANK, start=True, stop=True)
        elif level >= 1 and level <= 8:
            value = self.BRIGHTNESS | (level - 1)
            #print('level=', level, 'value=', hex(value)) #debug
            self.send_byte(value, start=True, stop=True)
        else:
            print('ERROR: Invalid brightness level')
    
    def set_text(self, text):
        data = [0] * self.N_DIGITS
        idx = 0
        for i in range(len(text)):
            ch = text[i]
            if ch not in self.FONT:
                print("ERROR: '{}' not in font table".format(ch))
                return False
            
            #Convert a char to segment data
            if ch == '.':
                if idx == 0:
                    print("EROR: Invalid decimal point location")
                    return False
                data[idx - 1] |= self.FONT[ch]
            else:
                data[idx] |= self.FONT[ch]
                idx += 1
                if idx >= self.N_DIGITS:
                    break

        # Send data buffer to LED
        self.send_byte(self.ADDR_C0H, start=True, stop=False)
        size = len(data)
        for i in range(size):
            self.send_byte(data[i], start=False, stop=(i == size-1))
        return True
