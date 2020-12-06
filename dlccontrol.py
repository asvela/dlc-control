# -*- coding: utf-8 -*-
"""
Convenience wrapper of Toptica Laser SDK for controlling a Toptica CTL with a DCL pro

Will check that wavelength setpoint and interal scan settings are within acceptable
ranges (will raise OutOfRangeError if not).

Todo:
* Handle scan outputs to OutA and OutB
* Make update of interdependent scan settings update all relevant private
  dictionary entries
* The frequency limits for interal scan are not correct

Andreas Svela // Dec 2020
"""

import sys
import time
import enum
import numpy as np
import toptica.lasersdk.dlcpro.v2_4_0 as toptica

_ip = "169.254.99.22"

class OutOfRangeError(ValueError):
    """Custom out of range errors"""

    def __init__(self, value, parameter_name: str, range: list):
        self.value = value
        self.parameter_name = parameter_name
        self.range = range
        self.message = f"{value} is not within the permitted {parameter_name} range {range}"
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
    OutA = 20
    OutB = 21

class InputChannel(enum.Enum):
    NotSelected = -3
    Fine1 = 0
    Fine2 = 1
    Fast3 = 2
    Fast4 = 3

class DLCcontrol:
    _is_open = False
    _remote_parameters = None
    _scan_parameters = None
    _lims = None

    def __init__(self, ip=_ip, open_on_init=True, **kwargs):
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
        self.define_internal_shorthands()
        self.update_scan_range()

    def close(self):
        if self._is_open:
            self.dlc.close()

    def get_limits_from_dlc(self):
        self._lims = {"wlmin": self.dlc.laser1.ctl.wavelength_min.get(),
                      "wlmax": self.dlc.laser1.ctl.wavelength_max.get(),
                      "vmin":  self.dlc.laser1.dl.pc.voltage_min.get(),
                      "vmax":  self.dlc.laser1.dl.pc.voltage_max.get(),
                      "cmin":  60.0, # lasing threshold
                      "cmax":  300.0,
                      "fmin":  0.02,
                      "fmax":  400} # cannot find max in manual
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

    def define_internal_shorthands(self):
        # constants
        self._vrange = [self._lims["vmin"], self._lims["vmax"]]
        self._crange = [self._lims["cmin"], self._lims["cmax"]]

    def update_scan_range(self, channel=None):
        if channel is None:
            channel = self._scan_parameters["output channel"]
        if channel == OutputChannel.CC:
            self._scan_range = self._crange
        elif channel == OutputChannel.PC:
            self._scan_range = self._vrange
        else:
            self._scan_range = [-np.inf, np.inf]
            print("(!) Warning: Scan range for OutA and OutB is not limted", flush=True)

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

    def check_value(self, val: float, parameter_name: str, range: list):
        """Check that a value is within a given range, raise error if not"""
        if not range[0] <= val <= range[1]:
            raise OutOfRangeError(val, parameter_name, range)

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
        """Analogue Remote Control for DLC pro can both current (cc)
        and voltage (pc) and be used simultaneously. In this wrapper
        both can be used simultaneously, but one must choose which
        is receiveing the commands at any given time with this select property"""
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
        """Choose which output channel to use for the ARC
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
        """The internal scan can only act on the piezo or the current at any
        given time
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
        self.dlc.laser1.scan.output_channel.set(num)
        self._scan_parameters["scan_output_channel"] = OutputChannel(num)
        self.update_scan_range(OutputChannel(num))

    @property
    def scan_frequency(self):
        return self.dlc.laser1.scan.frequency.get()

    @scan_frequency.setter
    def scan_frequency(self, val: float):
        val = float(val)
        self.check_value(val, "scan frequency", (self._lims["fmin"], self._lims["fmax"]))
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
        if min(new_range) < self._scan_range[0] or max(new_range) > self._scan_range[1]:
            raise OutOfRangeError(new_range, "scan", self._scan_range)
        self.dlc.laser1.scan.amplitude.set(val)
        self._scan_parameters["amplitude"] = val

    @property
    def scan_offset(self):
        return self.dlc.laser1.scan.offset.get()

    @scan_offset.setter
    def scan_offset(self, val: float):
        val = float(val)
        amplitude = self.scan_amplitude
        new_range = [val-amplitude/2, val+amplitude/2]
        if min(new_range) < self._scan_range[0] or max(new_range) > self._scan_range[1]:
            raise OutOfRangeError(new_range, "scan", self._scan_range)
        self.dlc.laser1.scan.offset.set(val)
        self._scan_parameters["offset"] = val

    @property
    def scan_start(self):
        return self.dlc.laser1.scan.start.get()

    @scan_start.setter
    def scan_start(self, val: float):
        val = float(val)
        self.check_value(val, "scan start", self._scan_range)
        self.dlc.laser1.scan.start.set(val)
        self._scan_parameters["start"] = val

    @property
    def scan_end(self):
        return self.dlc.laser1.scan.end.get()

    @scan_end.setter
    def scan_end(self, val: float):
        val = float(val)
        self.check_value(val, "scan end", self._scan_range)
        self.dlc.laser1.scan.end.set(val)
        self._scan_parameters["end"] = val



## Test and examples ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##

def show_all_parameters(ip=_ip):
    with DLCcontrol(ip) as dlc:
        print_dict(dlc.get_all_parameters(), header="All parameters that can be controlled with this wrapper")

def test(ip=_ip):
    with DLCcontrol(ip) as dlc:
        print_dict(dlc.get_scan_parameters())
        # print_dict(dlc.get_remote_parameters(), header="Remote parameters")
        # dlc.scan_output_channel = OutputChannel.PC


if __name__ == "__main__":
    # show_all_parameters()
    test()
