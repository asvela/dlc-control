# -*- coding: utf-8 -*-
"""
Example use of the dlccontrol module

(Word of caution: This module controls potentially Class 4 lasers.
Use is entirely on your own risk.)
"""

import dlccontrol as ctrl

_MY_LASER_IP = "169.254.99.22"


def properties_demo(ip=_MY_LASER_IP):
    with ctrl.DLCcontrol(ip) as dlc:
          dlc.wavelength_setpoint = 1550
          actual_wl = dlc.wavelength_actual
          # Set up a the analogue remote control sweeping the current with the
          # on input Fine1
          dlc.remote_select = "CC"
          dlc.remote_signal = "Fine1"
          dlc.remote_factor = 10
          dlc.remote_enable = True
          # Use the internal voltage scan and gradually increase the scan amplitude
          dlc.scan_output_channel = "PC"
          initial_amplitude = dlc.scan_amplitude
          dlc.scan_frequency = 20
          for i in range (10):
              dlc.scan_amplitude = i
           dlc.scan_amplitude = initial_amplitude


def show_all_parameters(ip=_MY_LASER_IP):
    with ctrl.DLCcontrol(ip) as dlc:
        print_dict(dlc.get_all_parameters(), header="All parameters that can be controlled with this wrapper")


def save_all_parameters(ip=_MY_LASER_IP, fname="laser_parameters"):
    with ctrl.DLCcontrol(ip) as dlc:
        dlc.save_parameters(fname)


def emission_control(ip=_MY_LASER_IP):
    with ctrl.DLCcontrol(ip) as dlc:
        print("Emission status:")
        dlc.verbose_emission_status()
        print("(!) WARNING Enabling laser current in three seconds")
        time.sleep(3)
        dlc.current_enabled = True
        dlc.verbose_emission_status()
        print("(!) Disabling laser current")
        dlc.current_enabled = False
        dlc.verbose_emission_status()
