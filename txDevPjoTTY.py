#!/usr/bin/python3
"""
Telex Device - Serial Communication over Pejjo's hardware module

Protocol:
tbd

"""
__author__      = "Per Johansson"
__email__       = "per@hoj.nu"
__copyright__   = "Copyright 2021, PJ"
__license__     = "GPL3"
__version__     = "0.0.1"

import serial
import time

import logging
l = logging.getLogger("piTelex." + __name__)

import txCode
import txBase
import log

#def LOG(text:str, level:int=3):
#    #log.LOG('\033[30;43m<'+text+'>\033[0m', level)

#######

class TelexPjoTTY(txBase.TelexBase):
    def __init__(self, **params):
        super().__init__()

        self.id = 'chT'
        self.params = params

        portname = params.get('portname', '/dev/ttyACM0')
        baudrate = params.get('baudrate', 50)
        bytesize = params.get('bytesize', 8)
        stopbits = params.get('stopbits', serial.STOPBITS_ONE_POINT_FIVE)
        coding = params.get('coding', 0)
        loopback = params.get('loopback', None)
        self._local_echo = params.get('loc_echo', False)

        self._rx_buffer = []
        self._tx_buffer = []
        self._counter_LTRS = 0
        self._counter_FIGS = 0
        self._counter_dial = 0
        self._time_last_dial = 0
        self._cts_stable = True   # rxd=Low
        self._state_counter = 0
        self._time_squelch = 0
        self._is_enabled = False
        self._is_online = False
        self._is_pending = False
        self._last_out_waiting = 0

        self._set_mode(params['mode'])
        if loopback is not None:
            self._loopback = loopback

        self._inverse_dtr = params.get('inverse_dtr', self._inverse_dtr)
        self._inverse_rts = params.get('inverse_rts', self._inverse_rts)

        # init serial
        self._tty = serial.Serial(portname, write_timeout=0)

        if baudrate not in self._tty.BAUDRATES:
            raise Exception('Baudrate not supported')
        if bytesize not in self._tty.BYTESIZES:
            raise Exception('Databits not supported')
        if stopbits not in self._tty.STOPBITS:
            raise Exception('Stopbits not supported')

        self._tty.baudrate = baudrate
        self._tty.bytesize = bytesize
        self._tty.stopbits = stopbits
        self._baudrate = baudrate

        # init codec
        #character_duration = (bytesize + 1.0 + stopbits) / baudrate
        character_duration = (bytesize + 3.0 ) / baudrate   # CH340 sends always with 2 stop bits
        self._mc = txCode.BaudotMurrayCode(self._loopback, coding=coding, character_duration=character_duration)

        self._set_enable(False)
        self._set_online(False)

    # -----

    def _set_mode(self, mode:str):
        self._loopback = False
        self._use_pulse_dial = False
        self._use_squelch = False
        self._use_cts = False
        self._inverse_cts = False
        #self._use_dtr = False
        self._inverse_dtr = False
        self._inverse_rts = False
        self._use_dedicated_line = True

        mode = mode.upper()

        if mode.find('TW39') >= 0:
            self._loopback = True
            self._use_cts = True
            self._use_pulse_dial = True
            self._use_squelch = True
            self._use_dedicated_line = False

        if mode.find('V21') >= 0:
            self._loopback = False
            self._use_cts = False
            self._use_squelch = False
            self._use_dedicated_line = False
            self._use_pulse_dial = False


    # -----

    def exit(self):
        self._tty.close()

    # -----

    def __del__(self):
        super().__del__()

    # =====

    def read(self) -> str:
        if self._tty.in_waiting:
            a = ''

            bb = self._tty.read(1)

            if bb and (not self._use_squelch or time.time() >= self._time_squelch):
                if self._is_enabled or self._use_dedicated_line:
                    if self._local_echo:
                        self._tty.write(bb)
                    
                    a = self._mc.decodeBM2A(bb)

                    if a:
                        self._check_special_sequences(a)

                elif self._is_online and self._use_pulse_dial:
                    b = bb[0]

                    if b == 0:   # break or idle mode
                        pass
                    elif (b & 0x13) == 0x10:   # valid dial pulse - min 3 bits = 40ms, max 5 bits = 66ms
                        self._counter_dial += 1
                        self._time_last_dial = time.time()

                self._cts_counter = 0

                if a:
                    self._rx_buffer.append(a)
                    #if self._local_echo:
                    #    self._tx_buffer.append(a)

        if self._rx_buffer:
            ret = self._rx_buffer.pop(0)
            return ret

    # -----

    def write(self, a:str, source:str):
        if len(a) != 1:
            self._check_commands(a)
            return 

        if a == '#':
            a = '@'   # ask teletype for hardware ID

        if a:
            if self._is_enabled or self._use_dedicated_line:
                self._tx_buffer.append(a)

    # =====

    def idle(self):
        if not self._use_squelch or time.time() >= self._time_squelch:
            if self._tx_buffer:
                #a = self._tx_buffer.pop(0)
                aa = ''.join(self._tx_buffer)
                self._tx_buffer = []
                bb = self._mc.encodeA2BM(aa)
                if bb:
                    self._tty.write(bb)
                    time.sleep(0.15) # Need to throttle somehow

    # -----

    def idle20Hz(self):
        time_act = time.time()

        if self._state_counter==0:
            if self._tty.ri==True:
                if not self._is_online:   # rxd=High
                    self._state_counter=20
                    self._rx_buffer.append('\x1bAT')
#                    self._rx_buffer.append('\x1bA')
                    pass
            elif self._tty.dsr ==False:   # logical xor
                if self._is_enabled:
                    self._state_counter=20
                    self._rx_buffer.append('\x1bST')
                    pass
            elif self._tty.dsr ==True and self._is_pending:
                # Confirm enable status for MCP
                self._rx_buffer.append('\x1b~0')
                self._is_pending=False

        elif self._state_counter>0:
            self._state_counter-=1


    # -----

    def idle2Hz(self):
        # send printer FIFO info
        out_waiting = self._tty.out_waiting
        if out_waiting != self._last_out_waiting and self._is_enabled:
            self._rx_buffer.append('\x1b~' + str(out_waiting))
            self._last_out_waiting = out_waiting

    # -----
#
    def _set_online(self, online:bool):
        self._is_online = online
        self._is_pending=True
        self._state_counter=20 # Let remote end confirm online
        if online:
            self._tty.rts = True
        else:
            self._tty.rts = False


    # -----

    def _set_enable(self, enable:bool):
        self._is_enabled = enable
        self._is_pending = True
        if enable:
            self._tty.dtr = True    # DTR -> True=Low=motor_on
        else:
            self._tty.dtr = False    # DTR -> True=Low=motor_on

        self._mc.reset()
        if self._use_squelch:
            self._set_time_squelch(0.5)
        #self._tty.send_break(1.0)

    # -----

    def _set_time_squelch(self, t_diff):
        t = time.time() + t_diff
        if self._time_squelch < t:
            self._time_squelch = t

    # -----

    def _set_pulse_dial(self, enable:bool):
        if not self._use_pulse_dial:
            return

        if enable:
            self._tty.baudrate = 75   # fix baudrate to scan number switch
        else:
            self._tty.baudrate = self._baudrate

    # =====

    def _check_special_sequences(self, a:str):
        if not self._use_cts:
            if a == '<':
                self._counter_LTRS += 1
                if self._counter_LTRS == 5:
                    self._rx_buffer.append('\x1bST')
            else:
                self._counter_LTRS = 0

            if a == '>':
                self._counter_FIGS += 1
                if self._counter_FIGS == 5:
                    self._rx_buffer.append('\x1bAT')
            else:
                self._counter_FIGS = 0

    # -----

    def _check_commands(self, a:str):
        enable = None

        if a == '\x1bA':
            self._set_pulse_dial(False)
            self._set_online(True)
            enable = True

        if a == '\x1bZ':
            self._tx_buffer = []    # empty write buffer...
            self._set_pulse_dial(False)
            self._set_online(False)
            enable = False   #self._use_dedicated_line
            if not enable and self._use_squelch:
                self._set_time_squelch(1.5)

        if a == '\x1bWB':
            self._set_online(True)
            if self._use_pulse_dial:   # TW39
                self._set_pulse_dial(True)
                self._tty.write(b'\x1E')   # send pulse with 25ms low to signal 'ready for dialing' ('Wahlbereitschaft')
                enable = False
            else:   # dedicated line, TWM, V.10
                enable = True

        if enable is not None:
            self._set_enable(enable)

#######
