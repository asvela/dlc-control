# -*- coding: utf-8 -*-
"""
Convenience wrapper of Toptica Laser SDK for controlling a Toptica CTL with a DCL pro

Will check that wavelength setpoint and interal scan settings are within acceptable
ranges (will raise OutOfRangeError if not).

Todo:
* Allow interal current scan to be used
* Make update of interdependent scan settings update all relevant private
  dictionary entries

Andreas Svela // 2020
"""

import sys
import time
import enum
import toptica.lasersdk.dlcpro.v2_4_0 as toptica

_ip = "169.254.99.22"

class OutOfRangeError(ValueError):
    """Custom out of range errors"""

    def __init__(self, value, parameter_name: str, permitted_range: list):
        self.value = value
        self.parameter_name = parameter_name
        self.range = permitted_range
        self.message = f"{value} is not within the permitted {parameter_name} range {permitted_range}"
        super().__init__(self.message)

def print_dict(d, indent=0, header=""):
    """Recursive dictionary printing"""
    longest_key_len = len(max(d.keys(), key=len))
    line = "-"*max(len(header), longest_key_len, 50)
    indent_spaces = " | "*indent
    if not indent:
        print("")
        if header:
            print(header)
        print(line)
    for key, val in d.items():
        if isinstance(val, dict):
            print(f"{indent_spaces}{key}:")
            print_dict(val, indent=(indent+1))
        else:
            print(indent_spaces, end="")
            print(f"{key:<{longest_key_len}}: {val}")
    if not indent:
        print(line)

class OutputChannel(enum.Enum):
    PC = 50
    CC = 51

class InputChannel(enum.Enum):
    Fine1 = 0
    Fine2 = 1
    Fast3 = 2
    Fast4 = 3

class DLCcontrol:
    _is_open = False
    _remote_parameters = None
    _scan_parameters = None
    _lims = None

    def __init__(self, ip=_ip, open_on_init=True):
        self.connection = toptica.NetworkConnection(ip)
        self.dlc = toptica.DLCpro(self.connection)
        if open_on_init:
            self.open()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def open(self):
        self.dlc.open()
        self._is_open = True
        self.get_limits_from_dlc()
        self.get_scan_parameters()
        self.get_remote_parameters()

    def close(self):
        if self._is_open:
            self.dlc.close()

    def get_limits_from_dlc(self):
        self._lims = {"wlmin": self.dlc.laser1.ctl.wavelength_min.get(),
                      "wlmax": self.dlc.laser1.ctl.wavelength_max.get(),
                      "vmin":  self.dlc.laser1.dl.pc.voltage_min.get(),
                      "vmax":  self.dlc.laser1.dl.pc.voltage_max.get(),
                      "cmin":  60.0, # lasing threshold
                      "cmax":  300.0}
        self._vrange = [self._lims["vmin"], self._lims["vmax"]] #shorthand
        self._crange = [self._lims["cmin"], self._lims["cmax"]] #shorthand
        return self._lims

    def get_scan_parameters(self):
        self._scan_parameters = {"enabled":        self.scan_enabled,
                                 "output channel": self.scan_output_channel,
                                 "frequency":      self.scan_frequency,
                                 "amplitude":      self.scan_amplitude,
                                 "offset":         self.scan_offset,
                                 "start":          self.scan_start,
                                 "end":            self.scan_end}
        return self._scan_parameters

    def get_remote_parameters(self):
        self._remote_parameters = {}
        for unit in ("cc", "pc"):
            self.remote_select = unit
            self._remote_parameters[unit] = {"enabled": self.remote_enabled,
                                             "factor": self.remote_factor,
                                             "signal": self.remote_signal}
        return self._remote_parameters

    def get_all_parameters(self):
        wls = {"wl setpoint": self.wavelength_setpoint,
               "wl actual": self.wavelength_actual}
        params = {"scan":            self.get_scan_parameters(), # updating scan parameters as they are interdependent
                  "analogue remote": self._remote_parameters,
                  "wavelength":      wls}
        return params

    def check_value(self, val: float, parameter_name: str, permitted_range: list):
        """Check that a value is within a given range, raise error if not"""
        if not permitted_range[0] <= val <= permitted_range[1]:
            raise OutOfRangeError(val, parameter_name, permitted_range)

    ## Emission properties ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##

    @property
    def emission(self):
        return self.dlc.emission.get()

    @emission.setter
    def emission(self, val):
        # Line below does not work, apparently not settable
        # self.dlc.emission_button_enabled.set(bool(val))
        raise NotImplementedError

    ## Wavelength properties ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##

    @property
    def wavelength_actual(self):
        return self.dlc.laser1.ctl.wavelength_act.get()

    @property
    def wavelength_setpoint(self):
        return self.dlc.laser1.ctl.wavelength_set.get()

    @wavelength_setpoint.setter
    def wavelength_setpoint(self, val: float):
        val = float(val)
        self.check_value(val, "wavelength setpoint", [self._lims["wlmin"], self._lims["wlmax"]])
        self.dlc.laser1.ctl.wavelength_set.set(val)

    ## Remote properties ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##

    @property
    def remote_select(self):
        return self._remote_str, self._remote_unit

    @remote_select.setter
    def remote_select(self, select: str):
        """Analogue Remote Control for DLC pro can target either current (cc)
        or voltage (pc), commands are otherwise the same"""
        if select.lower() == "cc":
            self._remote_str = "cc"
            self._remote_unit = self.dlc.laser1.dl.cc.external_input
        elif select.lower() == "pc":
            self._remote_str = "pc"
            self._remote_unit = self.dlc.laser1.dl.pc.external_input
        else:
            raise ValueError(f"select must be either 'pc' nor 'cc' (tried using '{select}')")

    @property
    def remote_enabled(self):
        return self._remote_unit.enabled.get()

    @remote_enabled.setter
    def remote_enabled(self, val: bool):
        self._remote_unit.enabled.set(val)
        self._remote_parameters[self._remote_str]["enabled"] = val

    @property
    def remote_signal(self):
        num = self._remote_unit.signal.get()
        return InputChannel(num)

    @remote_signal.setter
    def remote_signal(self, val):
        """Choose which output channel to use for the
        val : {"Fine1", "Fine2", "Fast3", "Fast4",
               InputChannel.Fine1, InputChannel.Fine2,
               InputChannel.Fast3, InputChannel.Fast4}"""
        try:
            if isinstance(val, InputChannel):
                num = val.value
            elif isinstance(val, str):
                num = InputChannel[val.title()].value
            else:
                raise KeyError
        except KeyError:
            raise ValueError( "Input channel must be one of 'Fine1', 'Fine2', "
                             f"'Fast3', 'Fast4', or an InputChannel (tried with '{val}')")
        self._remote_unit.signal.set(num)
        self._remote_parameters[self._remote_str]["signal"] = InputChannel(num)

    @property
    def remote_factor(self):
        return self._remote_unit.factor.get()

    @remote_factor.setter
    def remote_factor(self, val: float):
        val = float(val)
        self._remote_unit.factor.set(val)
        self._remote_parameters[self._remote_str]["factor"] = val

    ## Scan properties ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##

    @property
    def scan_enabled(self):
        return self.dlc.laser1.scan.enabled.get()

    @scan_enabled.setter
    def scan_enabled(self, val: bool):
        self.dlc.laser1.scan.enabled.set(val)
        self._scan_parameters["enabled"] = val

    @property
    def scan_output_channel(self):
        num = self.dlc.laser1.scan.output_channel.get()
        return OutputChannel(num)

    @scan_output_channel.setter
    def scan_output_channel(self, val):
        """The internal scan can only act on the piezo or the current
        val : {"CC", "PC", OutputChannel.CC, OutputChannel.PC}"""
        try:
            if isinstance(val, OutputChannel):
                num = val.value
            elif isinstance(val, str):
                num = OutputChannel[val.upper()].value
            else:
                raise KeyError
        except KeyError:
            raise ValueError( "Channel must be 'CC', 'PC', OutputChannel.CC, or "
                             f"OutputChannel.PC (tried with '{val}')")
        if num == OutputChannel["CC"].value:
            raise NotImplementedError("DLCcontrol can not yet handle out of range current scan values")
        self.dlc.laser1.scan.output_channel.set(num)
        self._scan_parameters["scan_output_channel"] = OutputChannel(num)

    @property
    def scan_frequency(self):
        return self.dlc.laser1.scan.frequency.get()

    @scan_frequency.setter
    def scan_frequency(self, val: float):
        val = float(val)
        self.check_value(val, "scan frequency", [0.02, 100])
        self.dlc.laser1.scan.frequency.set(val)
        self._scan_parameters["frequency"] = val

    @property
    def scan_amplitude(self):
        return self.dlc.laser1.scan.amplitude.get()

    @scan_amplitude.setter
    def scan_amplitude(self, val: float):
        val = float(val)
        offset = self.scan_offset
        new_range = [offset-val/2, offset+val/2]
        if min(new_range) < self._lims["vmin"] or max(new_range) > self._lims["vmax"]:
            raise OutOfRangeError(new_range, "voltage", self._vrange)
        self.dlc.laser1.scan.amplitude.set(val)
        self._scan_parameters["amplitude"] = val

    @property
    def scan_offset(self):
        return self.dlc.laser1.scan.offset.get()

    @scan_offset.setter
    def scan_offset(self, val: float):
        val = float(val)
        self.check_value(val, "scan offset", self._vrange)
        self.dlc.laser1.scan.offset.set(val)
        self._scan_parameters["offset"] = val

    @property
    def scan_start(self):
        return self.dlc.laser1.scan.start.get()

    @scan_start.setter
    def scan_start(self, val: float):
        val = float(val)
        self.check_value(val, "scan start", self._vrange)
        self.dlc.laser1.scan.start.set(val)
        self._scan_parameters["start"] = val

    @property
    def scan_end(self):
        return self.dlc.laser1.scan.end.get()

    @scan_end.setter
    def scan_end(self, val: float):
        val = float(val)
        self.check_value(val, "scan end", self._vrange)
        self.dlc.laser1.scan.end.set(val)
        self._scan_parameters["end"] = val



## Test and examples ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##

def show_all_parameters(ip=_ip):
    with DLCcontrol(ip) as dlc:
        print_dict(dlc.get_all_parameters(), header="All parameters that can be controlled with this wrapper")

def test(ip=_ip):
    with DLCcontrol(ip) as dlc:
        print_dict(dlc.get_scan_parameters())
        print_dict(dlc.get_remote_parameters(), header="Remote parameters")
        dlc.scan_start = 101
        dlc.scan_end = 140
        print_dict(dlc.get_scan_parameters())
        dlc.scan_output_channel = OutputChannel.CC


if __name__ == "__main__":
    # show_all_parameters()
    test()
