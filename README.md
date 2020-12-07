## DLC pro control

Convenience wrapper of Toptica Laser SDK for controlling a Toptica CTL with a DCL pro

Example use
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

versus the Toptica SDK

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
