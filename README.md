## Toptica DLCpro control

[![CodeFactor Grade](https://img.shields.io/codefactor/grade/github/asvela/dlc-control?style=flat-square)](https://www.codefactor.io/repository/github/asvela/dlc-control)
[![MIT License](https://img.shields.io/github/license/asvela/dlc-control?style=flat-square)](https://github.com/asvela/dlc-control/blob/main/LICENSE)

Convenience wrapper of Toptica Laser SDK for controlling a Toptica CTL with a DLCpro

*Word of caution: This module controls potentially Class 4 lasers.*
*Use is entirely on your own risk.*

API documentation available [here](https://asvela.github.io/dlc-control/).
Docs can be built with ``python3 -m pdoc --html -o ./docs dlccontrol.py`` (needs
pdoc3 to be installed).

The ``DLCcontrol`` class can read and control:

  * laser current on/off
  * wavelength setpoint for lasers that have this option
  * laser diode setpoint for lasers that have this option
  * analogue remote control settings (can control laser current and/or piezo simultaneously)
    - enable/disable
    - select input channel
    - set multiplier factor of the input voltage
  * internal scan settings (both for scanning the piezo and laser
    current)
    - scan start
    - scan end
    - scan offset
    - scan amplitude
  * user level (normal, maintenance, service)
  * any other setting using the ``DLCcontrol.client`` attribute


The class will check that the wavelength/temperature setpoint and internal scan 
settings are within acceptable ranges (and raise a ``OutOfRangeError`` if not).

The module also provides some convenient dictionaries with all the settings it
can modify, these dictionaries can be saved with measurement data to make sure
all settings are recorded. The ``DLCcontrol`` class can dump these dicts to
``json`` files.

Here are the parameters that can be saved, queried from the instrument and
printed with ``DLCcontrol.get_all_parameters(verbose=True)``:

```
-------------------------------------------------------
timestamp      : 2021-11-29 22:42:02.707762
scan:
 | enabled       : True
 | output channel: OutputChannel.PC
 | frequency     : 50.0000290562942
 | amplitude     : 21.0
 | offset        : 61.0
 | start         : 50.5
 | end           : 71.5
analogue remote:
 | cc:
 |  | enabled: False
 |  | factor : 10.0
 |  | signal : InputChannel.Fine1
 | pc:
 |  | enabled: False
 |  | factor : 10.0
 |  | signal : InputChannel.Fine2
wavelength:
 | wl setpoint: 1550.46
 | wl actual  : 1550.460841087153
temperatures:
 | temp setpoint: None
 | temp actual  : None
-------------------------------------------------------
```


### Comparison to the Topica laser SDK

The module uses properties extensively (listed as `Instance variables` in the
docs), which means class attributes have setter and getter functions,
which can be used like this:

```python
import dlccontrol as ctrl

with ctrl.DLCcontrol("xx.xx.xx.xx") as dlc:
    # Change wavelength or laser diode temperature depending on how the unit is
    # controlled
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
    dlc.scan_frequency = 20
    for i in range(10):
        dlc.scan_amplitude = i
      dlc.scan_amplitude = initial_amplitude
```

Doing the same with the Toptica SDK would look like this (and this module
is providing other features in addition to simplifying the syntax)

```python
import toptica.lasersdk.dlcpro.v2_4_0 as toptica
import toptica.lasersdk.decop as decop

with toptica.DLCpro(toptica.NetworkConnection("xx.xx.xx.xx")) as dlc:
    try:
        dlc.laser1.ctl.wavelength_set.set(float(1550))
        actual_wl = dlc.laser1.ctl.wavelength_act.get()
    except decop.DecopError:
        pass
    try:
        dlc.laser1.dl.tc.temp_set(float(20))
        actual_temp = dlc.laser1.dl.tc.temp_act.get()
    except decop.DecopError:
        pass
    # Set up a the analogue remote control sweeping the current with the
    # on input Fine1
    dlc.laser1.dl.cc.external_input.signal.set(0)
    dlc.laser1.dl.cc.external_input.factor.set(10)
    dlc.laser1.dl.cc.external_input.enable.set(True)
    # Use the internal voltage scan and gradually increase the scan amplitude
    dlc.laser1.scan.output_channel.set(50)
    initial_amplitude = dlc.laser1.scan.amplitude.get()
    dlc.laser1.scan.frequency.set(20)
    for i in range(10):
        dlc.laser1.scan.amplitude.set(float(i))
    dlc.laser1.scan.amplitude.set(initial_amplitude)
```

### Access any setting with `client`

If you want to access other settings than what the wrapper conveniently offers, 
the ``DLCcontrol.client`` attribute is useful as it can give you access to any other setting:

```python
import dlccontrol as ctrl
with ctrl.DLCcontrol("xx.xx.xx.xx") as dlc:
    print(dlc.client.get("serial-number"))
    # Need higher privilige to access the following commands
    dlc.set_user_level(1, "password from manual")
    dlc.client.set("laser1:dl:cc:current-clip", 250)
    dlc.client.set("laser1:dl:factory-settings:cc:current-clip", 250)
    dlc.client.exec("laser-common:store-all")
```

Note also the ``DLCcontrol.set_user_level()`` function to elevate the connection for access
to protected settings.

More examples are in the `examples.py` module.


### Todos & known issues

  * The upper frequency limit for internal scan is set very low, find out what
    the actual limits are for the voltage and current scan
  * Handle limits for scan outputs to ``OutA`` and ``OutB`` (they can currently
    be used, just no checks on the range)
  * Make update of interdependent scan settings update all relevant private
    dictionary entries
  * Set parameters from dict/file
  * Add property for setting the laser current when not scanning
  * Tests would be helpful...


### Source, contributions & license

The source is available on [Github](https://github.com/asvela/dlc-control/),
please report issues there. Contributions are also welcome.
The source code is licensed under the MIT license.


### Changelog

  * v0.2.0 Nov 2021: 
    - Added support for temperature tuned lasers, automatic discovery of whether 
      the laser is wavelength or temperature controlled
    - Adding a `client` attribute to the `DLCcontrol` class to access any laser
      attribute
    - Methods for setting and getting the user level for enabling change of
      restricted parameters
    - Parameters dictionary now includes timestamp of the parameter set
    - Black formatting