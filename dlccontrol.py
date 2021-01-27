# -*- coding: utf-8 -*-
"""
.. include:: ./README.md

"""

import os
import sys
import time
import enum
import json
import argparse
import numpy as np
import toptica.lasersdk.dlcpro.v2_4_0 as toptica

_IP_APOLLO = "169.254.99.22"

IP = _IP_APOLLO
"""The default IP when initialising a ``DLCcontrol()``"""

class OutOfRangeError(ValueError):
    """Custom out of range errors for when a parameter is outside the permitted
    range"""

    def __init__(self, value, parameter_name: str, permitted_range: list):
        self.value = value
        self.parameter_name = parameter_name
        self.range = permitted_range
        self.message = f"{value} is not within the permitted {parameter_name} range {permitted_range}"
        super().__init__(self.message)

def _print_dict(d, indent=0, header=""):
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
            _print_dict(val, indent=(indent+1))
        else:
            print(indent_spaces, end="")
            print(f"{key:<{longest_key_len}}: {val}")
    if not indent:
        print(line)

class OutputChannel(int, enum.Enum):  # int needed to avoid custom json serialiser
    """Output channel name to numeric value conversion"""
    PC = 50
    CC = 51
    OutA = 20
    OutB = 21

class InputChannel(int, enum.Enum):
    """Input channel name to numeric value conversion"""
    NotSelected = -3
    Fine1 = 0
    Fine2 = 1
    Fast3 = 2
    Fast4 = 3

# Dicts for converting between bools and text
_ON_OFF = {True: "on", False: "off"}
_ENABLED_DISABLED = {True: "enabled", False: "disabled"}


class DLCcontrol:
    """Control a Toptica DLC over an Ethernet connection

    Parameters
    ----------
    ip : str, default the module constant ``IP``
        Ip address of the DLC unit
    open_on_init : bool, default ``True``
        Decide if ``open()`` should be called during the initialisation of
        the class object
    """
    _is_open = False
    _remote_parameters = None
    _scan_parameters = None
    _lims = None
    calibration = None
    """MHz/mA or MHz/V calibration for the internal scan. Set by calling the
    ``freq_per_sec_internal_scan()`` method. After being set, the calibration
    will be kept in memory for future calls"""

    def __init__(self, ip=IP, open_on_init=True, **kwargs):
        self.connection = toptica.NetworkConnection(ip)
        self.dlc = toptica.DLCpro(self.connection)
        if open_on_init:
            self.open()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def open(self):
        """Open the connection to the laser and get all the parameters of the
        laser required to use the class"""
        self.dlc.open()
        self._is_open = True
        # Make sure all class sttributes are up to date
        self.get_limits_from_dlc()
        self.get_scan_parameters()
        self.get_remote_parameters()
        self._define_internal_shorthands()
        self._update_scan_range_attribute()

    def close(self):
        """Close the connection to the DLC"""
        if self._is_open:
            self.dlc.close()

    ## Limits and settings ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##

    def get_limits_from_dlc(self, verbose=False) -> dict:
        """Query the laser for the wavelength, piezo voltage, current and
        scan frequency limits, and populate the ``_lims`` dict attribute

        Returns
        -------
        self._lims : dict
            The limits
        """
        self._lims = {"wlmin": self.dlc.laser1.ctl.wavelength_min.get(),
                      "wlmax": self.dlc.laser1.ctl.wavelength_max.get(),
                      "vmin":  self.dlc.laser1.dl.pc.voltage_min.get(),
                      "vmax":  self.dlc.laser1.dl.pc.voltage_max.get(),
                      "cmin":  60.0, # lasing threshold
                      "cmax":  300.0,
                      "fmin":  0.02,
                      "fmax":  400} # cannot find max in manual
        if verbose:
            _print_dict(self._lims)
        return self._lims

    def _check_value(self, val: float, parameter_name: str, permitted_range: list):
        """Check that a value is within a given range, raise error if not

        Raises
        ------
        OutOfRangeError
            If ``val`` is not within the two values of the ``permitted_range``
            list
        """
        if not permitted_range[0] <= val <= permitted_range[1]:
            raise OutOfRangeError(val, parameter_name, permitted_range)

    def get_scan_parameters(self, verbose=False) -> dict:
        """Query the laser for the current scan settings, populate the
        ``_scan_parameters`` dict attribute

        Returns
        -------
        self._scan_parameters : dict
            All parameters for the internal scan
        """
        self._scan_parameters = {"enabled":        self.scan_enabled,
                                 "output channel": self.scan_output_channel,
                                 "frequency":      self.scan_frequency,
                                 "amplitude":      self.scan_amplitude,
                                 "offset":         self.scan_offset,
                                 "start":          self.scan_start,
                                 "end":            self.scan_end}
        if verbose:
            _print_dict(self._scan_parameters)
        return self._scan_parameters

    def _define_internal_shorthands(self):
        """Set these attributes as shorthands"""
        self._vrange = [self._lims["vmin"], self._lims["vmax"]]
        self._crange = [self._lims["cmin"], self._lims["cmax"]]

    def _update_scan_range_attribute(self, channel=None):
        if channel is None:
            channel = self._scan_parameters["output channel"]
        if channel == OutputChannel.CC:
            self._scan_range = self._crange
        elif channel == OutputChannel.PC:
            self._scan_range = self._vrange
        else:
            self._scan_range = [-np.inf, np.inf]
            print("(!) Warning: Scan range for OutA and OutB is not limted", flush=True)

    def get_remote_parameters(self, verbose=False):
        """Query the laser for the analogue remote control settings, and
        populate the ``_remote_parameters`` dict attribute

        Returns
        -------
        self._scan_parameters : dict
            All parameters for the analogue remote control
        """
        self._remote_parameters = {}
        for unit in ("cc", "pc"):
            self.remote_select = unit
            self._remote_parameters[unit] = {"enabled": self.remote_enabled,
                                             "factor": self.remote_factor,
                                             "signal": self.remote_signal}
        if verbose:
            _print_dict(self._remote_parameters)
        return self._remote_parameters

    def get_all_parameters(self, verbose=False) -> dict:
        """Returns an updated dictionary of all the parameters that can be set
        with the module

        Returns
        -------
        dict
            A nested dictionary with the parameters
        """
        wls = {"wl setpoint": self.wavelength_setpoint,
               "wl actual": self.wavelength_actual}
        params = {"scan":            self.get_scan_parameters(), # updating scan parameters as they are interdependent
                  "analogue remote": self._remote_parameters,
                  "wavelength":      wls}
        if verbose:
            _print_dict(params)
        return params

    def save_parameters(self, fname: str):
        """Grab an updated set of laser parameters and save to a ``json`` file

        Raises
        ------
        RuntimeError
            If a file with name `fname` already exists
        """
        params = self.get_all_parameters()
        if not fname[-4:] == ".json":
            fname += ".json"
        if os.path.exists(fname):
            raise RuntimeError(f"File '{fname}' already exists")
        with open(fname, 'w') as outfile:
            json.dump(params, outfile)

    @staticmethod
    def read_parameters(fname: str, verbose=True) -> dict:
        """Read (but not set!) parameters from json file"""
        if not fname[-4:] == ".json":
            fname += ".json"
        with open(fname) as json_file:
            params = json.load(json_file)
        if verbose:
            _print_dict(params)
        return params

    def set_parameters(self, params: dict):
        """*Not yet implemented*

        The idea is to be able to use the parameters in a dict and set them
        accordingly"""
        raise NotImplementedError("Still to be implemented")

    def verbose_emission_status(self):
        """Print the emission status of the laser, for example
        ```
        Emission button is ENABLED
        Laser current is DISABLED
        Therefore, emission is ON
        ```
        """
        print(f"Emission button is {_ENABLED_DISABLED[self.emission_button]}")
        print(f"Laser current is {_ENABLED_DISABLED[self.current_enabled]}")
        print(f"Therefore, emission is {_ON_OFF[self.emission]}")

    def freq_per_sec_internal_scan(self, calibration=None):
        """Calculate frequency span per second for the laser in MHz per second
        from the scan parameters

        Parameters
        ----------
        calibration : float
            [MHz/mA or MHz/V]
        """
        params = self.get_scan_parameters()
        scan_freq = params["frequency"]
        peak_to_peak = params["amplitude"]
        if calibration is not None:
            self.calibration = calibration
        return freq_per_sec(scan_freq, peak_to_peak, scaling=1, calibration=self.calibration)

    ## Emission properties ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##

    @property
    def emission(self) -> bool:
        """Emission status of the DLC (read only)"""
        return self.dlc.emission.get()

    @property
    def emission_button(self) -> bool:
        """Status of the emission button of the DLC (read only)"""
        return self.dlc.emission_button_enabled.get()

    @property
    def current_enabled(self) -> bool:
        """Status of the current to the laser"""
        return self.dlc.laser1.dl.cc.enabled.get()

    @current_enabled.setter
    def current_enabled(self, val: bool):
        """Sneaky way to control emission on/off provided the button on the
        DLC is enabled"""
        if val and not self.emission_button:
            print("(!) Emission button on DLC not enabled, so cannot enable emission")
        self.dlc.laser1.dl.cc.enabled.set(val)

    ## Wavelength properties ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##

    @property
    def wavelength_actual(self) -> float:
        """The actual wavelength of the laser (read only)"""
        return self.dlc.laser1.ctl.wavelength_act.get()

    @property
    def wavelength_setpoint(self) -> float:
        """The setpont of the laser wavelength"""
        return self.dlc.laser1.ctl.wavelength_set.get()

    @wavelength_setpoint.setter
    def wavelength_setpoint(self, val: float):
        val = float(val)
        self._check_value(val, "wavelength setpoint", [self._lims["wlmin"], self._lims["wlmax"]])
        self.dlc.laser1.ctl.wavelength_set.set(val)

    ## Remote properties ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##

    @property
    def remote_select(self) -> tuple:
        """Analogue Remote Control for both the DLCpro's current (cc)
        and voltage (pc) can be used simultaneously. With this class, both can
        be used simultaneously, with this select property choosing which remote
        is receiveing the commands at any given time

        Example
        -------

            with DLCcontrol(ip) as dlc:
                # Choose to set the ARC for the current
                dlc.remote_select = "CC"
                # Decide its input..
                dlc.remote_signal = "Fine1"
                # ..and enable it
                dlc.remote_enable = True
                # Now move to the ARC for the piezo..
                dlc.remote_select = "PC"
                # ..and choose some settings for it
                dlc.remote_signal = "Fast3"
                dlc.remote_enable = True

        """
        return self._remote_str, self._remote_unit

    @remote_select.setter
    def remote_select(self, select: str):
        """
        select : {"pc", "cc"}
        """
        if select.lower() == "cc":
            self._remote_str = "cc"
            self._remote_unit = self.dlc.laser1.dl.cc.external_input
        elif select.lower() == "pc":
            self._remote_str = "pc"
            self._remote_unit = self.dlc.laser1.dl.pc.external_input
        else:
            raise ValueError(f"select must be either 'pc' nor 'cc' (tried using '{select}')")

    @property
    def remote_enabled(self) -> bool:
        """Status of the chosen remote"""
        return self._remote_unit.enabled.get()

    @remote_enabled.setter
    def remote_enabled(self, val: bool):
        self._remote_unit.enabled.set(val)
        self._remote_parameters[self._remote_str]["enabled"] = val

    @property
    def remote_signal(self) -> InputChannel:
        """The input port the chosen remote uses"""
        num = self._remote_unit.signal.get()
        return InputChannel(num)

    @remote_signal.setter
    def remote_signal(self, val: InputChannel):
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
    def remote_factor(self) -> float:
        """The numerical factor the remote signal is multiplied with before used
        as the current or piezo control"""
        return self._remote_unit.factor.get()

    @remote_factor.setter
    def remote_factor(self, val: float):
        val = float(val)
        self._remote_unit.factor.set(val)
        self._remote_parameters[self._remote_str]["factor"] = val

    ## Scan properties ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##

    @property
    def scan_enabled(self) -> bool:
        """Internal scan on/off"""
        return self.dlc.laser1.scan.enabled.get()

    @scan_enabled.setter
    def scan_enabled(self, val: bool):
        self.dlc.laser1.scan.enabled.set(val)
        self._scan_parameters["enabled"] = val

    @property
    def scan_output_channel(self) -> OutputChannel:
        """Internal scan output channel. It can be directed to the
        piezo or laser current directly, or to the output BNCs on the DLC"""
        num = self.dlc.laser1.scan.output_channel.get()
        return OutputChannel(num)

    @scan_output_channel.setter
    def scan_output_channel(self, val):
        """The internal scan can only act on eiter piezo or the current at any
        given time, or be directed to the DLC BNCs
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
        self._update_scan_range_attribute(OutputChannel(num))

    @property
    def scan_frequency(self) -> float:
        """Internal scan frequency"""
        return self.dlc.laser1.scan.frequency.get()

    @scan_frequency.setter
    def scan_frequency(self, val: float):
        val = float(val)
        self._check_value(val, "scan frequency", (self._lims["fmin"], self._lims["fmax"]))
        self.dlc.laser1.scan.frequency.set(val)
        self._scan_parameters["frequency"] = val

    @property
    def scan_amplitude(self) -> float:
        """Internal scan amplitude"""
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
    def scan_offset(self) -> float:
        """Internal scan offset value"""
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
    def scan_start(self) -> float:
        """Internal scan start value"""
        return self.dlc.laser1.scan.start.get()

    @scan_start.setter
    def scan_start(self, val: float):
        val = float(val)
        self._check_value(val, "scan start", self._scan_range)
        self.dlc.laser1.scan.start.set(val)
        self._scan_parameters["start"] = val

    @property
    def scan_end(self) -> float:
        """Interal scan end value"""
        return self.dlc.laser1.scan.end.get()

    @scan_end.setter
    def scan_end(self, val: float):
        val = float(val)
        self._check_value(val, "scan end", self._scan_range)
        self.dlc.laser1.scan.end.set(val)
        self._scan_parameters["end"] = val


def freq_per_sec(scan_freq, peak_to_peak, scaling, calibration):
    """Calculate frequency sweep per second for the laser in MHz per second

    Parameters
    ----------
    scan_freq : float
        [Hz]
    peak_to_peak : float
        [Vpp]
    scaling : float
        [mA/V or V/V]
    calibration : float
        [MHz/mA or MHz/V]
    """
    scan_period = 1/(2*scan_freq) #sec
    # (division by two because of triangle wave and hence in practice
    #  sweeping double the speed)
    current_span = peak_to_peak*scaling #mA
    return current_span*calibration/scan_period #MHz/second


def freq_per_sec_from_params(params, calibration):
    """Calculate frequency sweep per second for the laser in MHz per second due
    to the internal scan using a params dictionary

    Parameters
    ----------
    params : dict
        As provided by ``DLCcontrol.get_all_parameters()`` or a ``json`` file
    calibration : float
        [MHz/mA or MHz/V]
    """
    scan_freq = params["scan"]["frequency"]
    peak_to_peak = params["scan"]["amplitude"]
    return freq_per_sec(scan_freq, peak_to_peak, scaling=1, calibration=calibration)


## A programme ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ##

def step_through_scan_range(ip=IP, steps=20, dlc=None):
    """A simple programme: Step through the internal voltage/current
    scan range currently in use

    Parameters
    ----------
    ip : str
        IP of the DLC if a connection should be opened
    steps : int, default 20
        The number of steps to divide the amplitude into
    dlc : DLCcontrol, optional
        If a ``DLCcontrol`` object is provided, a new one will not be created
    """
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


def command_line_programme():
    """Command line use of the module: run ``python dlccontrol.py -h`` to see
    the options"""
    parser = argparse.ArgumentParser(description='A few useful laser control funtions')
    parser.add_argument('-i', '--ip', type=str, default="",
                        help=f"The ip of the laser (defaults to {IP})")
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
    ip = args.ip if args.ip else IP
    with DLCcontrol(ip) as dlc:
        if args.emission:
            dlc.verbose_emission_status()
        if args.parameters:
            params = dlc.get_all_parameters(verbose=True)
        if args.fname is not None:
            dlc.save_parameters(args.folder+args.fname)
        if args.steps:
            step_through_scan_range(ip, args.steps, dlc)


if __name__ == "__main__":
    command_line_programme()
