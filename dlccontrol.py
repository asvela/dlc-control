# -*- coding: utf-8 -*-
"""
Convenience wrapper of Toptica Laser SDK for controlling a Toptica CTL with a DCL pro

Will check that wavelength setpoint and interal scan settings are within acceptable
ranges (will raise OutOfRangeError if not).

Todo:
* Handle limits for scan outputs to OutA and OutB (they can currently be used,
  just no checks on the range)
* Make update of interdependent scan settings update all relevant private
  dictionary entries
* Set parameters from dict
* Set current when not scanning

Notes:
* The upper frequency limit for interal scan is set very low

(Word of caution: This module controls potentially Class 4 lasers.
Use is entirely on your own risk.)

Andreas Svela // Dec 2020
"""

import os
import sys
import time
import enum
import json
import argparse
import numpy as np
import toptica.lasersdk.dlcpro.v2_4_0 as toptica

_ip_apollo = "169.254.99.22"
_ip = _ip_apollo

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

class OutputChannel(int, enum.Enum): # int needed to avoid custom json serialiser
    PC = 50
    CC = 51
    OutA = 20
    OutB = 21

class InputChannel(int, enum.Enum):
    NotSelected = -3
    Fine1 = 0
    Fine2 = 1
    Fast3 = 2
    Fast4 = 3

# Dicts for converting between bools and text
_on_off = {True: "on", False: "off"}
_enabled_disabled = {True: "enabled", False: "disabled"}


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
        # Make sure all class sttributes are up to date
        self.get_limits_from_dlc()
        self.get_scan_parameters()
        self.get_remote_parameters()
        self.define_internal_shorthands()
        self.update_scan_range_attribute()

    def close(self):
        if self._is_open:
            self.dlc.close()

    ## Limits and settings ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##

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

    def check_value(self, val: float, parameter_name: str, range: list):
        """Check that a value is within a given range, raise error if not"""
        if not range[0] <= val <= range[1]:
            raise OutOfRangeError(val, parameter_name, range)

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

    def update_scan_range_attribute(self, channel=None):
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
        """Returns an updated dictionary of all the parameters that can be set
        with the module"""
        wls = {"wl setpoint": self.wavelength_setpoint,
               "wl actual": self.wavelength_actual}
        params = {"scan":            self.get_scan_parameters(), # updating scan parameters as they are interdependent
                  "analogue remote": self._remote_parameters,
                  "wavelength":      wls}
        return params

    def save_parameters(self, fname):
        """Grab an updated set of laser parameters and save to a json file"""
        params = self.get_all_parameters()
        if not fname[-4:] == ".json":
            fname += ".json"
        if os.path.exists(fname):
            raise RuntimeError(f"File '{fname}' already exists")
        with open(fname, 'w') as outfile:
            json.dump(params, outfile)

    def load_parameters(self, fname, print_result=True):
        """Load (but not set!) parameters from json file"""
        if not fname[-4:] == ".json":
            fname += ".json"
        with open(fname) as json_file:
            params = json.load(json_file)
        if print_result:
            print_dict(params)
        return params

    def set_parameters(self, params: dict):
        raise NotImplementedError("Still to be implemented")

    def verbose_emission_status(self):
        print(f"Emission button is {_enabled_disabled[self.emission_button]}")
        print(f"Laser current is {_enabled_disabled[self.current_enabled]}")
        print(f"Therefore, emission is {_on_off[self.emission]}")

    ## Emission properties ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##

    @property
    def emission(self):
        return self.dlc.emission.get()

    @property
    def emission_button(self):
        return self.dlc.emission_button_enabled.get()

    @property
    def current_enabled(self):
        return self.dlc.laser1.dl.cc.enabled.get()

    @current_enabled.setter
    def current_enabled(self, val: bool):
        """Sneaky way to control emission on/off provided the button on the
        DLCpro is enabled"""
        if val and not self.emission_button:
            print("(!) Emission button on DLC not enabled, so cannot enable emission")
        self.dlc.laser1.dl.cc.enabled.set(val)

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
        self.update_scan_range_attribute(OutputChannel(num))

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



## Examples ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##

def show_all_parameters(ip=_ip):
    with DLCcontrol(ip) as dlc:
        print_dict(dlc.get_all_parameters(), header="All parameters that can be controlled with this wrapper")

def save_all_parameters(ip=_ip, fname="laser_parameters"):
    with DLCcontrol(ip) as dlc:
        dlc.save_parameters(fname)

def step_through_scan_range(ip=_ip, steps=20, dlc=None):
    """Step through the internal voltage/current scan range currently in use"""
    if dlc is None:
        dlc = DLCcontrol(ip)
        close_flag = True
    else:
        close_flag = False
    # Read initial values
    initial_end = dlc.scan_end
    initial_offset = dlc.scan_offset
    initial_amplitude = dlc.scan_amplitude
    # Define range to scan
    range = np.linspace(0, -initial_amplitude, steps)
    try:
        dlc.scan_amplitude = 0
        for i, change in enumerate(range):
            try:
                print(f"{i}: change to {initial_end+change:.3f}V")
                try:
                    dlc.scan_offset = initial_end + change
                except dlc.OutOfRangeError as e:
                    print(e)
                    break
                time.sleep(1)
            except KeyboardInterrupt:
                print("Stopping scan")
                break
    finally:
        print("Restore initial state")
        dlc.scan_offset = initial_offset
        dlc.scan_amplitude = initial_amplitude
        if close_flag:
            dlc.close()

def emission_control_demo(ip=_ip):
    with DLCcontrol(ip) as dlc:
        print("Emission status:")
        dlc.verbose_emission_status()
        print("(!) WARNING Enabling laser current in three seconds")
        time.sleep(3)
        dlc.current_enabled = True
        dlc.verbose_emission_status()
        print("(!) Disabling laser current")
        dlc.current_enabled = False
        dlc.verbose_emission_status()

def main():
    parser = argparse.ArgumentParser(description='A few useful laser control funtions')
    parser.add_argument('-i', '--ip', type=str, default="",
                        help=f"The ip of the laser (defaults to {_ip})")
    parser.add_argument('-e', '--emission-status', dest='emission', action='store_true',
                        help="Print the emission status of the device")
    parser.add_argument('-p', '--parameters', action='store_true',
                            help="Print the laser parameters")
    parser.add_argument('-s', '--save-filename', dest='fname', type=str, default=None,
                        help=("Save all laser parameters to a json file to filename"))
    parser.add_argument('-f', '--folder', type=str, default="./",
                        help=("Select a folder for storing saved files if different "
                                  "from the folder where the script is exectuted"))
    parser.add_argument('-n', '--steps', type=int, default=0,
                        help=("Scan discretely through the current laser span in <STEPS>"))
    args = parser.parse_args()
    ip = args.ip if args.ip else _ip
    with DLCcontrol(ip) as dlc:
        if args.emission:
            dlc.verbose_emission_status()
        if args.parameters:
            params = dlc.get_all_parameters()
            print_dict(params)
        if args.fname is not None:
            dlc.save_parameters(args.folder+args.fname)
        if args.steps:
            step_through_scan_range(ip, args.steps, dlc)

if __name__ == "__main__":
    main()
