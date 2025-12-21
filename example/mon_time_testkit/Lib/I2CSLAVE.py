from machine import Pin, SoftI2C
from time import sleep,sleep_us
from timeout import *

class I2CSLAVE:

    HWADR=const(0b1100011) # 0x63

    def __init__(self,scl=18,sda=19,freq=1000,hwadr=HWADR):
        self.clock=Pin(scl,Pin.IN)
        self.data=Pin(sda,Pin.IN)
        self.freq=freq
        self.HWADR=hwadr
        self.puls=int(1000000/freq/2) #us
        self.stop=False
        print("Slave started @ {} Hz".format(freq))
        
    def devAddress(self,adr=None):
        if adr is None:
            return self.HWADR
        else:
            self.HWADR=(adr & 0xff)
    
    def frequency(self,freq=None):
        if freq is None:
            return self.freq
        else:
            self.freq=freq
            self.puls=int(1000000/freq/2)

    def setIdle(self):
        self.clock(Pin.IN)
        self.data(Pin.IN)

    def waitDataLow(self):
        while self.data.value()==1:
            pass
        
    def waitClockLow(self):
        while self.clock.value()==1:
            pass

    def waitClockHigh(self):
        while self.clock.value()==0:
            pass
        
    def awaitStart(self):
        while self.clock.value()==1:
            if self.data.value()==0:
                while self.clock.value()==1:
                    pass

    def awaitStop(self):
        self.waitDataLow()
        self.waitClockHigh()
        sleep_us(self.puls*2)
        return self.data.value()==1

    def readByte(self):
        byte=0
        self.stop=False
        for i in range(8):
            self.waitClockHigh()
            byte = ((byte )<<1 ) | self.data.value()
            self.waitClockLow()
        return byte

    def writeByte(self,byte):
        self.waitClockLow()
        self.data.init(Pin.OUT)
        mask=0x80
        for i in range(0,8):
            bit=byte & mask
            if bit:
                self.data.value(1)
            else:
                self.data.value(0)
            mask=mask >> 1
            self.waitClockHigh()
            self.waitClockLow()
        self.data.init(Pin.IN)

    def sendAck(self,ack):
        self.waitClockLow()
        self.data.init(Pin.OUT,value=ack) # access data
        self.waitClockHigh()
        self.waitClockLow()
        self.data.init(Pin.IN)# release data
        
    def awaitAck(self):
        self.waitClockLow()
        self.waitClockHigh()
        ackBit=self.data.value()
        self.waitClockLow()
        return ackBit