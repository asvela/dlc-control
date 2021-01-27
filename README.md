## Toptica DLC pro control

![CodeFactor Grade](https://img.shields.io/codefactor/grade/github/asvela/dlc-control?style=flat-square)

Convenience wrapper of Toptica Laser SDK for controlling a Toptica CTL with a DCL pro

*Word of caution: This module controls potentially Class 4 lasers.*
*Use is entirely on your own risk.*

The ``DLCcontrol`` class can read and control:

  * laser current on/off
  * wavelength setpoint
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


The class will check that wavelength setpoint and internal scan settings are
within acceptable ranges (and raise a ``OutOfRangeError`` if not).


### Examples

The module uses properties extensively (listed as `Instance variables` in the
docs), which means class attributes have setter and getter functions,
which can be used like this:

```python
import dlccontrol as ctrl

with ctrl.DLCcontrol("xx.xx.xx.xx") as dlc:
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
```

Doing the same with the Toptica SDK would look like this (and this module
is providing a lot of other features in addition to simplifying the syntax)

```python
import toptica.lasersdk.dlcpro.v2_4_0 as toptica

with toptica.DLCpro(toptica.NetworkConnection("xx.xx.xx.xx")) as dlc:
        dlc.laser1.ctl.wavelength_set.set(float(1550))
        actual_wl = dlc.laser1.ctl.wavelength_act.get()
        # Set up a the analogue remote control sweeping the current with the
        # on input Fine1
        dlc.laser1.dl.cc.external_input.signal.set(0)
        dlc.laser1.dl.cc.external_input.factor.set(10)
        dlc.laser1.dl.cc.external_input.enable.set(True)
        # Use the internal voltage scan and gradually increase the scan amplitude
        dlc.laser1.scan.output_channel.set(50)
        initial_amplitude = dlc.laser1.scan.amplitude.get()
        dlc.laser1.scan.frequency.set(20)
        for i in range (10):
            dlc.laser1.scan.amplitude.set(float(i))
        dlc.laser1.scan.amplitude.set(initial_amplitude)
```

More examples are in the `examples.py` module.

The module also provides some convenient dictionaries with all the settings it
can modify, these dictionaries can be saved with measurement data to make sure
all settings are recorded. The ``DLCcontrol`` class can dump these dicts to
``json`` files.

Here is a nested dictionary printed with the module's
`_print_dict()` function:

```
-------------------------------------------------------
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
-------------------------------------------------------
```


### Todos & known issues

  * The upper frequency limit for internal scan is set very low, find out what
    the actual limits are for the voltage and current scan
  * Handle limits for scan outputs to ``OutA`` and ``OutB`` (they can currently
    be used, just no checks on the range)
  * Make update of interdependent scan settings update all relevant private
    dictionary entries
  * Set parameters from dict/file
  * Add property for setting the laser current when not scanning


### Source, contributions & license

The source is available on [Github](https://github.com/asvela/dlc-control/),
please report issues there. Contributions are also welcome.
The source code is licensed under the MIT license.


### Documentation

Docs can be built with ``python3 -m pdoc --html -o ./docs dlccontrol.py``

Available on [Github pages](https://asvela.github.io/dlc-control/)
