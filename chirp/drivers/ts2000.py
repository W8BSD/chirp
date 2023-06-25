# Copyright 2012 Tom Hayward <tom@tomh.us>
# Copyright 2012 Tom Hayward <tom@tomh.us>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import re
from chirp import chirp_common, directory, util, errors
from chirp.drivers.kenwood_d7 import KenwoodD7Family
from chirp.settings import RadioSetting, RadioSettingGroup, \
    RadioSettingValueString

# It would be nice to have this as an array so it's grouped in the right
# Unfortunately, when we do that, we can't have labels for each line
class Kenwoodts2000DTMFMemory(RadioSettingGroup):
    DTMF_CHARSET = "ABCD#*0123456789 "

    def __init__(self, name, shortname, radio, *args, **kwargs):
        super().__init__(name, shortname, *args, **kwargs)
        self._radio = radio
        self._name = name
        index = self._get_index()
        rs = RadioSetting("EX04501%s0" % index, "Memory Name",
                          RadioSettingValueString(0, 8, '', False))
        self.append(rs)
        rs = RadioSetting("EX04501%s1" % index, "Memory Value",
                          RadioSettingValueString(0, 16, '', False,
                                                  self.DTMF_CHARSET))
        self.append(rs)

    def _get_index(self):
        return self._name[7:8]

    def read_setting_from_radio(self):
        index = self._get_index()
        vname = self._radio._kenwood_get("EX04501%s0" % index)[1]
        value = self._radio._kenwood_get("EX04501%s1" % index)[1]
        self["EX04501%s0" % index].value.set_value(vname)
        self["EX04501%s0" % index].value._has_changed = False
        self["EX04501%s1" % index].value.set_value(value)
        self["EX04501%s1" % index].value._has_changed = False

    def changed(self):
        for element in self:
            if element.changed():
                return True
        return False

    def set_setting_to_radio(self):
        for element in self:
            if not element.changed():
                continue
            value = element.value.get_value()
            # These are deleted by using a space as the first character
            # TODO: Don't allow entering a space as the first character
            if value == '':
                value = ' '
            if value[0:1] == ' ':
                value = ' '
            self._radio._kenwood_set(element.get_name(),
                                     value)
            element.value._has_changed = False


@directory.register
class TS2000Radio(KenwoodD7Family):
    """Kenwood TS-2000"""
    MODEL = "TS-2000"
    HARDWARE_FLOW = False

    _ARG_DELIMITER = ""
    # 9600 is the default, so it would make sense for it to be first,
    # but I use 57600 and I want it fast fast fast!
    _BAUDS = [57600, 38400, 19200, 9600, 4800]
    _CMD_DELIMITER = ";"
    # Send ID after to force a response
    _DISABLE_AI_CMD = ('AI0;ID',)
    _DUPLEX = {0: "", 1: "+", 2: "-", 3: "=", 4: "split"}
    _HAS_NAME = False
    _ID_STRING = "019"
    _MODES = {1: "LSB", 2: "USB", 3: "CW", 4: "FM",
              5: "AM", 6: "FSK", 7: "CW-R", 9: "FSK-R"}
    _SSB_STEPS = (1, 2.5, 5, 10)
    _FM_STEPS = (5.0, 6.25, 10.0, 12.5, 15.0, 20.0, 25.0, 30.0, 50.0, 100.0)
    _TMODES = ["", "Tone", "TSQL", "DTCS"]
    _TONES = tuple([x for x in chirp_common.OLD_TONES if x != 69.3])
    _TONE_STRS = tuple([str(x) for x in _TONES])
    _UPPER = 289

    _CALL_CHANS = ()
    _SPECIAL_CHANS = ("290 Start", "290 End",
                      "291 Start", "291 End",
                      "292 Start", "292 End",
                      "293 Start", "293 End",
                      "294 Start", "294 End",
                      "295 Start", "295 End",
                      "296 Start", "296 End",
                      "297 Start", "297 End",
                      "298 Start", "298 End",
                      "299 Start", "299 End")
    _PROGRAMMABLE_VFOS = ()

    def get_features(self, *args, **kwargs):
        rf = super().get_features(*args, **kwargs)
        rf.has_dtcs = True
        rf.has_bank = False
        rf.valid_modes = ["LSB", "USB", "CW", "FM", "AM",
                          "FSK", "CW-R", "FSK-R"]
        rf.valid_tmodes = list(self._TMODES)
        rf.valid_tuning_steps = list(self._SSB_STEPS + self._FM_STEPS)
        rf.valid_bands = [(1000, 1300000000)]
        rf.valid_duplexes = list(self._DUPLEX.values())

        # TS-2000 uses ";" as a message separator even though it seems to
        # allow you to to use all printable ASCII characters at the manual
        # controls.  The radio doesn't send the name after the ";" if you
        # input one from the manual controls.
        rf.valid_characters = chirp_common.CHARSET_ASCII.replace(';', '')
        rf.valid_name_length = 7    # 7 character channel names
        return rf

    def _kenwood_set(self, cmd, value):
        self._do_prerequisite(cmd, False, True)
        resp = self._command(cmd + value + self._CMD_DELIMITER + cmd)
        self._do_prerequisite(cmd, False, False)
        if resp != cmd + self._ARG_DELIMITER + value:
            raise errors.RadioError("Radio refused to set %s" % cmd)

    def _kenwood_simple_get(self, cmd):
        resp = self._command(cmd)
        if resp[0:len(cmd)] == cmd:
            return (cmd, resp[len(cmd):])
        else:
            if resp == cmd:
                return [resp, ""]
            else:
                raise errors.RadioError("Radio refused to return %s" % cmd)

    def _parse_id_response(self, resp):
        # most kenwood HF radios
        if resp[-5:-3] == 'ID':
            return resp[-3:]
        return None

    def _get_range_end_mem(self, index):
        base = index - self._UPPER - 1
        end = base % 2
        base = int(base / 2)
        return (end, base + self._UPPER + 1)

    def _cmd_set_memory_or_split(self, memid, memory, split):
        # Add the ID at the end to force a response from the rig
        # since we don't want AI mode
        index = self._memid_to_index(memid)
        sd = split and 1 or 0
        if index > self._UPPER:
            if split:
                raise errors.RadioError("Can't set split on start/end "
                                        "memories")
            memstr = "%d%03d" % self._get_range_end_mem(index)
        else:
            memstr = "%d%s" % (sd, memid)
        if memory.empty:  # Erase
            return "MW%s%035i;ID" % (memstr, 0)
        if split:
            spec = self._make_split_spec(memid, memory)
        else:
            spec = self._make_mem_spec(memid, memory)
        return "MW%s%s;ID" % (memstr, ''.join(spec))

    def _cmd_get_memory_or_split(self, memid, split):
        sd = split and 1 or 0
        index = self._memid_to_index(memid)
        if index > self._UPPER:
            if split:
                return None
            memstr = "%d%03d" % self._get_range_end_mem(index)
        else:
            memstr = "%d%s" % (sd, memid)
        return "MR%s" % (memstr)

    def _cmd_recall_memory(self, memid):
        return "MC%s" % (memid)

    def _cmd_cur_memory(self):
        return "MC"

    def _cmd_erase_memory(self, number):
        # write a memory channel that's effectively zeroed except
        # for the channel number
        return "MW%04i%035i" % (number, 0)

    def _parse_mem(self, spec):
        mem = chirp_common.Memory()

        # pad string so indexes match Kenwood docs
        spec = " " + spec

        # use the same variable names as the Kenwood docs
        # _p1 = spec[3]
        _p2 = spec[4]
        _p3 = spec[5:7]
        _p4 = spec[7:18]
        _p5 = spec[18]
        _p6 = spec[19]
        _p7 = spec[20]
        _p8 = spec[21:23]
        _p9 = spec[23:25]
        _p10 = spec[25:28]
        # _p11 = spec[28]
        _p12 = spec[29]
        _p13 = spec[30:39]
        _p14 = spec[39:41]
        # _p15 = spec[41]
        _p16 = spec[42:49]

        mnum = int(_p2 + _p3)     # concat bank num and chan num
        if mnum > self._UPPER:
            mnum = self._UPPER + ((mnum - self._UPPER) * 2) - 1
            if spec[3] == '1':
                mnum += 1;
            # TODO: This doesn't do what we want... there doesn't seem
            # to be an obvious way to have a different list for specific
            # memories.
            # mem._valid_map['duplex'] = ["", "+", "-"]
            mem.extd_number = self._index_to_memid(mnum)
        mem.number = mnum

        if _p5 == '0':
            # NOTE(danms): Apparently some TS2000s will return unset
            # memory records with all zeroes for the fields instead of
            # NAKing the command with an N response. If that happens here,
            # return an empty memory.
            mem.empty = True
            if mem.number > self._UPPER and spec[3] == '1':
                    mem.immutable = ['name', 'tmode', 'rtone', 'ctone',
                                     'dtcs', 'duplex', 'offset', 'mode',
                                     'tuning_step', 'skip']
            return mem

        mem.freq = int(_p4)

        mem.mode = self._MODES[int(_p5)]
        if mem.mode in ["AM", "FM"]:
            mem.tuning_step = self._FM_STEPS[int(_p14)]
        else:
            mem.tuning_step = self._SSB_STEPS[int(_p14)]
        # TODO: When we change a "start" memory, we need to refresh
        #       the corresponding "end" memory
        if mem.number > self._UPPER and spec[3] == '1':
                mem.immutable = ['name', 'tmode', 'rtone', 'ctone',
                                 'dtcs', 'duplex', 'offset', 'mode',
                                 'tuning_step', 'skip']
                return mem
        mem.skip = ["", "S"][int(_p6)]
        mem.tmode = self._TMODES[int(_p7)]
        # PL and T-SQL are 1 indexed, DTCS is 0 indexed
        mem.rtone = self._TONES[int(_p8) - 1]
        mem.ctone = self._TONES[int(_p9) - 1]
        mem.dtcs = chirp_common.DTCS_CODES[int(_p10)]
        mem.duplex = self._DUPLEX[int(_p12)]
        mem.offset = int(_p13)      # 9-digit
        mem.name = _p16

        return mem

    def _parse_split(self, mem, spec):

        # pad string so indexes match Kenwood docs
        spec = " " + spec

        # use the same variable names as the Kenwood docs
        split_freq = int(spec[7:18])
        if mem.freq != split_freq:
            mem.duplex = "split"
            mem.offset = split_freq

        return mem

    def _make_mem_spec(self, memid, mem):
        if mem.duplex in " +-":
            duplex = util.get_dict_rev(self._DUPLEX, mem.duplex)
            offset = mem.offset
        elif mem.duplex == "split":
            duplex = 0
            offset = 0
        else:
            LOG.error("Bug: unsupported duplex `%s'" % mem.duplex)
        if mem.mode in ["AM", "FM"]:
            step = self._FM_STEPS.index(mem.tuning_step)
        else:
            step = self._SSB_STEPS.index(mem.tuning_step)

        # TS-2000 won't accept channels with tone mode off if they have
        # tone values
        if mem.tmode == "":
            rtone = 0
            ctone = 0
            dtcs = 0
        else:
            # PL and T-SQL are 1 indexed, DTCS is 0 indexed
            rtone = (self._TONES.index(mem.rtone) + 1)
            ctone = (self._TONES.index(mem.ctone) + 1)
            dtcs = (chirp_common.DTCS_CODES.index(mem.dtcs))

        spec = (
            "%011i" % mem.freq,
            "%i" % (util.get_dict_rev(self._MODES, mem.mode)),
            "%i" % (mem.skip == "S"),
            "%i" % self._TMODES.index(mem.tmode),
            "%02i" % (rtone),
            "%02i" % (ctone),
            "%03i" % (dtcs),
            "0",    # REVERSE status
            "%i" % duplex,
            "%09i" % offset,
            "%02i" % step,
            "0",    # Memory Group number (0-9)
            "%s" % mem.name,
        )

        return spec

    def _make_split_spec(self, memid, mem):
        if mem.duplex in " +-":
            duplex = util.get_dict_rev(self._DUPLEX, mem.duplex)
        elif mem.duplex == "split":
            duplex = 0
        else:
            LOG.error("Bug: unsupported duplex `%s'" % mem.duplex)
        if mem.mode in ["AM", "FM"]:
            step = self._FM_STEPS.index(mem.tuning_step)
        else:
            step = self._SSB_STEPS.index(mem.tuning_step)

        # TS-2000 won't accept channels with tone mode off if they have
        # tone values
        if mem.tmode == "":
            rtone = 0
            ctone = 0
            dtcs = 0
        else:
            # PL and T-SQL are 1 indexed, DTCS is 0 indexed
            rtone = (self._TONES.index(mem.rtone) + 1)
            ctone = (self._TONES.index(mem.ctone) + 1)
            dtcs = (chirp_common.DTCS_CODES.index(mem.dtcs))

        spec = (
            "%011i" % mem.offset,
            "%i" % (util.get_dict_rev(self._MODES, mem.mode)),
            "%i" % (mem.skip == "S"),
            "%i" % self._TMODES.index(mem.tmode),
            "%02i" % (rtone),
            "%02i" % (ctone),
            "%03i" % (dtcs),
            "0",    # REVERSE status
            "%i" % duplex,
            "%09i" % 0,
            "%02i" % step,
            "0",    # Memory Group number (0-9)
            "%s" % mem.name,
        )

        return spec

    _BOOL = {'type': 'bool'}
    _DTMF_MEMORY = {'type': Kenwoodts2000DTMFMemory}
    _INT_ZERO_TO_NINE = {'type': 'integer', 'min': 0, 'max': 9}
    _OFF_TO_NINE = {'type': 'list',
                    'values': ('Off', '1', '2', '3', '4', '5', '6', '7',
                               '8', '9')}
    _LINEAR_CONTROL_DELAY = {'type': 'list',
                    'values': ('Off', '10ms TX delay', '25ms TX delay')}
    _DSP_EQ = {'type': 'list',
               'values': ('Off', 'High Boost', 'Formant (Voice) Pass',
                          'Bass Boost',
                          'Conventional (+3dB at 600 Hz and higher)',
                          'User')}
    _CW_DOT_DASH_RATIOS = list([str(float(x)/10) for x in range(25, 41, 1)])
    _CW_DOT_DASH_RATIOS.insert(0, 'Auto')
    _CW_DOT_DASH_RATIO_VALUES = tuple(_CW_DOT_DASH_RATIOS)
    _PACKET_BAUD = {'type': 'list',
                    'values': ('1200 bps', '9600 bps')}
    _MAIN_SUB = {'type': 'list',
                 'values': ('Main', 'Sub')}
    _CALLSIGN = {'type': 'string', 'max_len': 9,
                 'charset': 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-'}
    _PF_BUTTONS = {'type': 'map',
                   'map': (("Menu 0", "00"), ("Menu 1", "01"),
                           ("Menu 2", "02"), ("Menu 3", "03"),
                           ("Menu 4", "04"), ("Menu 5", "05"),
                           ("Menu 6", "06"), ("Menu 7", "07"),
                           ("Menu 8", "08"), ("Menu 9", "09"),
                           ("Menu 10", "10"), ("Menu 11", "11"),
                           ("Menu 12", "12"), ("Menu 13", "13"),
                           ("Menu 14", "14"), ("Menu 15", "15"),
                           ("Menu 16", "16"), ("Menu 17", "17"),
                           ("Menu 18", "18"), ("Menu 19", "19"),
                           ("Menu 20", "20"), ("Menu 21", "21"),
                           ("Menu 22", "22"), ("Menu 23", "23"),
                           ("Menu 24", "24"), ("Menu 25", "25"),
                           ("Menu 26", "26"), ("Menu 27", "26"),
                           ("Menu 28", "28"), ("Menu 29", "29"),
                           ("Menu 30", "30"), ("Menu 31", "31"),
                           ("Menu 32", "32"), ("Menu 33", "33"),
                           ("Menu 34", "34"), ("Menu 35", "35"),
                           ("Menu 36", "36"), ("Menu 37", "37"),
                           ("Menu 38", "38"), ("Menu 39", "39"),
                           ("Menu 40", "40"), ("Menu 41", "41"),
                           ("Menu 42", "42"), ("Menu 43", "43"),
                           ("Menu 44", "44"), ("Menu 45", "45"),
                           ("Menu 46", "46"), ("Menu 47", "47"),
                           ("Menu 48", "48"), ("Menu 49", "49"),
                           ("Menu 50", "50"), ("Menu 51", "51"),
                           ("Menu 52", "52"), ("Menu 53", "53"),
                           ("Menu 54", "54"), ("Menu 55", "55"),
                           ("Menu 56", "56"), ("Menu 57", "57"),
                           ("Menu 58", "58"), ("Menu 59", "59"),
                           ("Menu 60", "60"), ("Menu 61", "61"),
                           ("Menu 62", "62"), ("Voice 1", "63"),
                           ("Voice 2", "64"), ("RX Moni", "65"),
                           ("DSP Moni", "66"), ("Quick Memo MR", "67"),
                           ("Quick Memo M.In", "68"), ("Split", "69"),
                           ("TF-SET", "70"), ("A/B", "71"),
                           ("VFO/M", "72"), ("A=B", "73"),
                           ("Scan", "74"), ("M→VFO", "75"),
                           ("M.In", "76"), ("CW Tune", "77"),
                           ("CH1", "78"), ("CH2", "79"),
                           ("CH3", "80"), ("Fine", "81"),
                           ("CLR", "82"), ("Call", "83"),
                           ("Ctrl", "84"), ("1 MHz", "85"),
                           ("ANT1/2", "86"), ("NB", "87"),
                           ("N.R.", "88"), ("B.C.", "89"),
                           ("A.N.", "90"), ("No Function", "99"))}
    _SETTINGS = {
        'EX0000000': {'type': 'list',
                      'values': ('Off', '1', '2', '3', '4')},
        'EX0010000': _BOOL,
        'EX0020000': {'type': 'list',
                      'values': ('500', '1000')},
        'EX0030000': _BOOL,
        'EX0040000': _BOOL,
        'EX0050000': _BOOL,
        'EX0060100': _BOOL,
        'EX0060200': _BOOL,
        'EX0070000': _BOOL,
        'EX0080000': {'type': 'list',
                      'values': ('100', '200', '300', '400', '500')},
        'EX0090000': _BOOL,
        'EX0100000': {'type': 'list',
                      'values': ('TO', 'CO')},
        'EX0110000': {'type': 'list',
                      'values': ('31 Channel', '61 Channel',
                                 '91 Channel', '181 Channel')},
        'EX0120000': _OFF_TO_NINE,
        'EX0130000': _OFF_TO_NINE,
        'EX0140000': _OFF_TO_NINE,
        'EX0150000': _OFF_TO_NINE,
        'EX0160000': {'type': 'list',
                      'values': ('Main/Sub Mix on Both',
                                 'SP1 (L) Main, SP2 (R) Sub',
                                 'SP1 (L) Main + ¼ Sub, '
                                 'SP2 (R) Sub + ¼ Main')},
        'EX0170000': _BOOL,
        'EX0180000': _BOOL,
        'EX0190100': _BOOL,
        'EX0190200': {'type': 'list',
                      'values': ('Off', '150ms', '250ms', '500ms')},
        'EX0200000': _DSP_EQ,
        'EX0210000': _DSP_EQ,
        'EX0220000': {'type': 'list',
                      'values': ('2.0 kHz', '2.2 kHz', '2.4 kHz',
                                 '2.6 kHz', '2.8 kHz', '3.0 kHz')},
        'EX0230000': _BOOL,
        'EX0240000': {'type': 'list',
                      'values': ('Off', '3 minutes', '5 minutes',
                                 '10 minutes', '20 minutes', '30 minutes')},
        'EX0250000': _BOOL,
        'EX0260000': _BOOL,
        'EX0270000': _BOOL,
        'EX0280100': _LINEAR_CONTROL_DELAY,
        'EX0280200': _LINEAR_CONTROL_DELAY,
        'EX0280300': _LINEAR_CONTROL_DELAY,
        'EX0280400': _LINEAR_CONTROL_DELAY,
        'EX0280500': _LINEAR_CONTROL_DELAY,
        'EX0290100': _BOOL,
        'EX0290200': {'type': 'integer', 'min': 0, 'max': 60},
        'EX0300000': _BOOL,
        'EX0310000': {'type': 'list',
                      'values': tuple(['%d Hz' % x for x in range(400, 1001,
                                                                  50)])},
        'EX0320000': {'type': 'list',
                      'values': ('1ms', '2ms', '4ms', '6ms')},
        'EX0330000': {'type': 'list',
                      'values': _CW_DOT_DASH_RATIO_VALUES},
        'EX0340000': _BOOL,
        'EX0350000': _BOOL,
        'EX0360000': _BOOL,
        'EX0370000': _BOOL,
        'EX0380000': {'type': 'list',
                      'values': ('170 Hz', '200 Hz', '425 Hz', '850 Hz')},
        'EX0390000': {'type': 'list',
                      'values': ('Normal', 'Inverse')},
        'EX0400000': {'type': 'list',
                      'values': ('1275 Hz', '2125 Hz')},
        'EX0410000': {'type': 'list',
                      'values': ('Low', 'Mid', 'High')},
        'EX0420000': {'type': 'list',
                      'values': ('Burst', 'Continuous')},
        'EX0430000': _BOOL,
        'EX0440000': _BOOL,
        'EX045010': _DTMF_MEMORY,
        'EX045011': _DTMF_MEMORY,
        'EX045012': _DTMF_MEMORY,
        'EX045013': _DTMF_MEMORY,
        'EX045014': _DTMF_MEMORY,
        'EX045015': _DTMF_MEMORY,
        'EX045016': _DTMF_MEMORY,
        'EX045017': _DTMF_MEMORY,
        'EX045018': _DTMF_MEMORY,
        'EX045019': _DTMF_MEMORY,
        'EX0450200': {'type': 'list',
                      'values': ('Slow', 'Fast')},
        'EX0450300': {'type': 'list',
                      'values': ('100ms', '250ms', '500ms', '750ms',
                                 '1000ms', '1500ms', '2000ms')},
        'EX0450400': _BOOL,
        'EX0460000': _MAIN_SUB,
        'EX0470000': _PACKET_BAUD,
        'EX0480000': {'type': 'list',
                      'values': ('TNC Band', 'Main & Sub')},
        'EX0490100': {'type': 'list',
                      'values': ('Auto', 'Manual')},
        'EX0490200': {'type': 'list',
                      'values': ('Off', 'Morse', 'Voice')},
        'EX0500100': _BOOL,
        'EX0500200': _INT_ZERO_TO_NINE,
        'EX0500300': _INT_ZERO_TO_NINE,
        'EX0500400': _INT_ZERO_TO_NINE,
        'EX0500500': _MAIN_SUB,
        'EX0500600': _PACKET_BAUD,
        'EX0510100': _PF_BUTTONS,
        'EX0510200': _PF_BUTTONS,
        'EX0510300': _PF_BUTTONS,
        'EX0510400': _PF_BUTTONS,
        'EX0510500': _PF_BUTTONS,
        'EX0520000': _BOOL,
        'EX0530000': _BOOL,
        'EX0540000': _BOOL,
        # Inverted... with leading space... whee!
        'TC': {'type': 'map',
                'map': (('Off', ' 1'), ('On', ' 0'))},
        'EX0560000': {'type': 'list',
                      'values': ('4800 bps', '9600 bps', '19200 bps',
                                 '38400 bps', '57600 bps')},
        'EX0570000': {'type': 'list',
                      'values': ('Off', '60min', '120min', '180min')},
        'EX0580000': {'type': 'list',
                      'values': ('Font 1', 'Font 2')},
        'EX0590000': {'type': 'integer', 'min': 1, 'max': 16},
        'EX0600000': {'type': 'list',
                      'values': ('Negative', 'Positive')},
        'EX0610100': {'type': 'list',
                      'values': ('Off', 'Locked-Band', 'Cross-Band')},
        'EX0610200': _BOOL,
        'EX0610300': {'type': 'integer', 'min': 0, 'max': 999},
        'EX0610400': _BOOL,
        'EX0610500': _BOOL,
        'EX0620100': _CALLSIGN,
        'EX0620200': _CALLSIGN,
        'EX0620300': {'type': 'list',
                      'values': _TONE_STRS},
        'EX0620400': _PACKET_BAUD,
        'EX0620500': {'type': 'list',
                      'values': ('Off', 'Client', 'Commander', 'Transporter')},
    }

    _SETTINGS_MENUS = (
        ('Operator Interface',
            (("EX0000000", "Display Brightness"),
             ("EX0010000", "Key Illumination"))),
        ('Tuning Control',
            (('EX0020000', 'Tuning control change per revolution'),
             ('EX0030000', 'Tuning with MULTI/ CH control'),
             ('EX0040000', 'Rounds off VFO frequencies changed by using the '
                           'MULTI/ CH control'),
             ('EX0050000', '9 kHz frequency step size for the MULTI/ CH '
                           'control in AM mode on the AM broadcast band'))),
        ('Memory Channel',
            (('EX0060100', 'Memory-VFO split operation'),
             ('EX0060200', 'Tunable (ON) or fixed (OFF) memory channel '
                           'frequencies'))),
        ('Scan Operation',
            (('EX0070000', 'Program scan partially slowed'),
             ('EX0080000', 'Slow down frequency range for the Program scan'),
             ('EX0090000', 'Program scan hold'),
             ('EX0100000', 'Scan resume method'),
             ('EX0110000', 'Visual scan range'))),
        ('Monitor Sound',
            (('EX0120000', 'Beep output level'),
             ('EX0130000', 'TX sidetone volume'),
             ('EX0140000', 'DRU-3A playback volume'),
             ('EX0150000', 'VS-3 playback volume'))),
        ('Speaker Output',
            (('EX0160000', 'Audio output configuration for EXT.SP2 '
                           'or headphone'),
             ('EX0170000', 'Reverses the EXT.SP1 and EXT.SP2 (the headphone '
                           'jack L/R channels) audio outputs'))),
        ('RX Antenna',
            (('EX0180000', 'Enable an input from the HF RX ANT connector'),)),
        ('S-meter Squelch',
            (('EX0190100', 'Enable S-meter squelch'),
             ('EX0190200', 'Hang time for S-meter squelch'))),
        ('DSP Equalizer',
            (('EX0200000', 'DSP RX equalizer'),
             ('EX0210000', 'DSP TX equalizer'))),
        ('DSP Filter', (('EX0220000', 'DSP Filter'),)),
        ('Fine Tuning', (('EX0230000', 'Fine transmit power tuning'),)),
        ('TOT', (('EX0240000', 'Time-out timer'),)),
        ('Transverter', (('EX0250000', 'Transverter frequency display'),)),
        ('Antenna Tuner',
            (('EX0260000', 'TX hold when AT completes the tuning'),
             ('EX0270000', 'In-line AT while receiving'))),
        ('Linear Amplifier',
            (('EX0280100', 'Linear amplifier control delay for HF band'),
             ('EX0280200', 'Linear amplifier control delay for 50 MHz band'),
             ('EX0280300', 'Linear amplifier control delay for 144 MHz band'),
             ('EX0280400', 'Linear amplifier control delay for '
                           '430/ 440 MHz band'),
             ('EX0280500', 'Linear amplifier control delay for '
                           '1.2 GHz band'))),
        ('Message Playback',
            (('EX0290100', 'Repeat the playback'),
             ('EX0290200', 'Interval time for repeating the playback'))),
        ('CW',
            (('EX0300000', 'Keying priority over playback'),
             ('EX0310000', 'CW RX pitch/ TX sidetone frequency'),
             ('EX0320000', 'CW rise time'),
             ('EX0330000', 'CW keying dot, dash weight ratio'),
             ('EX0340000', 'Reverse CW keying auto weight ratio'),
             ('EX0350000', 'Bug key mode'),
             ('EX0360000', 'Auto CW TX in SSB mode'),
             ('EX0370000', 'Frequency correction for changing SSB to CW'))),
        ('FSK',
            (('EX0380000', 'FSK shift'),
             ('EX0390000', 'FSK keying polarity'),
             ('EX0400000', 'FSK tone frequency'))),
        ('FM',
            (('EX0410000', 'Mic gain for FM'),
             ('EX0420000', 'Sub-tone mode for FM'),
             ('EX0430000', 'Auto repeater offset'),
             ('EX0440000', 'TX hold: 1750 Hz tone'))),
        ('DTMF',
            (('DTMF number memory select',
                (('EX045010', "Memory 0"),
                 ('EX045011', "Memory 1"),
                 ('EX045012', "Memory 2"),
                 ('EX045013', "Memory 3"),
                 ('EX045014', "Memory 4"),
                 ('EX045015', "Memory 5"),
                 ('EX045016', "Memory 6"),
                 ('EX045017', "Memory 7"),
                 ('EX045018', "Memory 8"),
                 ('EX045019', "Memory 9"))),
             ('EX0450200', 'TX speed for stored DTMF number'),
             ('EX0450300', 'Pause duration for stored DTMF number'),
             ('EX0450400', 'Enable Mic remote control'))),
        ('TNC',
            (('EX0460000', 'MAIN/ SUB band: Internal TNC'),
             ('EX0470000', 'Data transfer speed: Internal TNC'),
             ('EX0480000', 'DCD sensing band'),
             ('P.C.T. (Packet Cluster Tune) mode',
                (('EX0490100', 'Packet Cluster Tune mode'),
                 ('EX0490200', 'Packet Cluster RX confirmation tone'))),
             ('Packet configuration',
                (('EX0500100', 'Packet filter bandwidth'),
                 ('EX0500200', 'AF input level for Packet'),
                 ('EX0500300', 'MAIN band AF output level for '
                               'packet operation'),
                 ('EX0500400', 'SUB band AF output level for '
                               'packet operation'),
                 ('EX0500500', 'MAIN/ SUB band: External TNC'),
                 ('EX0500600', 'Data transfer speed: External TNC'))))),
        ('PF keys',
            (('EX0510100', 'Front panel PF key'),
             ('EX0510200', 'Microphone PF1 (CALL) key'),
             ('EX0510300', 'Microphone PF2 (VFO) key'),
             ('EX0510400', 'Microphone PF3 (MR) key'),
             ('EX0510500', 'Microphone PF4 (PF) key'))),
        ('Master/ Slave operation',
            (('EX0520000', 'Split frequency transfer in '
                           'master/slave operation'),
             ('EX0530000', 'Permit to write the transferred Split frequencies '
                           'to the target VFOs'))),
        ('TX Inhibit', (('EX0540000', 'TX Inhibit'),)),
        ('Packet',
            (('TC ', 'Packet communication mode'),
             ('EX0560000', 'COM port communication speed'))),
        ('APO', (('EX0570000', 'APO (Auto Power Off) function'),)),
        ('RC-2000 Configuration',
            (('EX0580000', 'RC-2000 font in easy operation mode'),
             ('EX0590000', 'RC-2000 panel/ TS-2000(X) '
                           'dot-matrix display contrast'),
             ('EX0600000', 'Display mode for RC-2000'))),
        # The rest of the groups are K-Type Only
        ('Repeater Functions',
            (('EX0610100', 'Repeater mode select'),
             ('EX0610200', 'Repeater TX hold'),
             ('EX0610300', 'Remote control ID code'),
             ('EX0610400', 'Acknowledgement signal in external '
                           'remote control mode'),
             ('EX0610500', 'External remote control'))),
        ('Sky Command II+',
            (('EX0620100', 'Commander callsign for Sky Command II+'),
             ('EX0620200', 'Transporter callsign for Sky Command II+'),
             ('EX0620300', 'Sky Command II+ tone frequency'),
             ('EX0620400', 'Sky Command II+ communication speed'),
             ('EX0620500', 'Sky Command II+ mode'))))
