# -*- coding: utf-8 -*-
"""
Example use of the dlccontrol module

(Word of caution: This module controls potentially Class 4 lasers.
Use is entirely on your own risk.)
"""

import time
import dlccontrol as ctrl

MY_LASER_IP = "169.254.99.22"


def properties_demo(ip=MY_LASER_IP):
    with ctrl.DLCcontrol(ip) as dlc:
        if dlc.wl_setting_present:
            dlc.wavelength_setpoint = 1550
            actual_wl = dlc.wavelength_actual
        if dlc.temp_setting_present:
            dlc.temp_setpoint = 20
            actual_temp = dlc.temp_actual
        # Set up a the analogue remote control sweeping the current with the
        # on input Fine1
        dlc.remote_select = "CC"
        dlc.remote_signal = "Fine1"
        dlc.remote_factor = 10
        dlc.remote_enable = True
        # Use the internal voltage scan and gradually increase the scan amplitude
        dlc.scan_output_channel = "PC"
        initial_amplitude = dlc.scan_amplitude
        dlc.scan_frequency = 20.5
        for i in range(10):
            dlc.scan_amplitude = i
        dlc.scan_amplitude = initial_amplitude


def show_all_parameters(ip=MY_LASER_IP):
    with ctrl.DLCcontrol(ip) as dlc:
        print("All parameters that can be controlled with this wrapper")
        dlc.get_all_parameters(verbose=True)


def save_all_parameters(ip=MY_LASER_IP, fname="laser_parameters"):
    with ctrl.DLCcontrol(ip) as dlc:
        dlc.save_parameters(fname)


def emission_control(ip=MY_LASER_IP):
    with ctrl.DLCcontrol(ip) as dlc:
        print("\nEmission status:\n")
        dlc.verbose_emission_status()
        print("\n(!) WARNING Enabling laser current in three seconds..\n")
        time.sleep(3)
        dlc.current_enabled = True
        dlc.verbose_emission_status()
        print("\n(!) Disabling laser current")
        dlc.current_enabled = False
        dlc.verbose_emission_status()
