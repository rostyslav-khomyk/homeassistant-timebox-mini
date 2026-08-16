# homeassistant-timebox-mini
[![hacs_badge](https://img.shields.io/badge/custom%20repository%20for-HACS-%2303a9f4.svg?style=flat-square&logo=homeassistant&logoColor=white)](https://hacs.xyz/) ![hacs_badge](https://img.shields.io/github/languages/top/rostyslav-khomyk/homeassistant-timebox-mini?style=flat-square)

Divoom Timebox Mini custom service component for Home Assistant.

Timebox protocol extracted from [ScR4tCh/timebox](https://github.com/ScR4tCh/timebox)

### Table of content
* [Limitations](#limitations)
* [Requirements](#requirements)
  * [Requirements](#bluetooth-hardware)
  * [Home Assistant installation](#home-assistant-installation)
* [Setup instructions](#setup-instructions)
  * [Copying into custom_components folder](#copying-into-custom_components-folder)
  * [Enabling the custom_component](#enabling-the-custom_component)
* [Troubleshooting](#troubleshooting)
* [Create your own picture / animation](#create-your-own-picture--animation)
  * [Picture](#picture)
  * [Animation](#animation)
* [TODO](#todo)
    
The Divoom Timebox Mini is a Bluetooth speaker with a 11x11 RGB LED matrix.

![Timebox Mini](https://raw.githubusercontent.com/rostyslav-khomyk/homeassistant-timebox-mini/main/res/timebox-mini.jpg)

This component allow to run the following actions on your Timebox Mini from a HomeAssistant service:
- Set the clock automatically from your system clock
- Display the clock
- Set the audio volume level
- Set the LED brightness level
- Display the weather information (you have to use Divoom phone app to send weather info to your timebox)
- Display moving text with configurable text color, background color, speed, repeat count, and direction
- Display a picture/animation from predefined choices (see [matrices](custom_components/timebox_mini/matrices) and [animations](custom_components/timebox_mini/animations) folders) :

<img src="https://raw.githubusercontent.com/rostyslav-khomyk/homeassistant-timebox-mini/main/res/timebox-mini-homeassistant.png" width="200"/><img src="https://raw.githubusercontent.com/rostyslav-khomyk/homeassistant-timebox-mini/main/res/timebox-mini-hourglass.png" width="200"/><img src="https://raw.githubusercontent.com/rostyslav-khomyk/homeassistant-timebox-mini/main/res/timebox-mini-locked.png" width="200"/><img src="https://raw.githubusercontent.com/rostyslav-khomyk/homeassistant-timebox-mini/main/res/timebox-mini-unlocked.png" width="200"/><img src="https://raw.githubusercontent.com/rostyslav-khomyk/homeassistant-timebox-mini/main/res/timebox-mini-small-bell.png" width="200"/><img src="https://raw.githubusercontent.com/rostyslav-khomyk/homeassistant-timebox-mini/main/res/timebox-mini-green-check.png" width="200"/><img src="https://raw.githubusercontent.com/rostyslav-khomyk/homeassistant-timebox-mini/main/res/timebox-mini-red-cross.png" width="200"/><img src="https://raw.githubusercontent.com/rostyslav-khomyk/homeassistant-timebox-mini/main/res/timebox-mini-orange-warning.png" width="200"/>

## Limitations
This service cannot be used to control multiple Divoom devices from one HomeAssistant instance:

To display custom content, a Bluetooth connection has to be established between the computer and your Divoom speaker when calling the service for the first time.

If you try to control another Divoom device, the connection to the first device will be stopped and the device will display a blinking "Bluetooth" symbol trying to reconnect. This is a Divoom limitation.

## Requirements
### Bluetooth Hardware
This component uses Python sockets for Bluetooth communication.

Any Bluetooth hardware supported by your operating system should work. The Bluetooth interface of the Raspberry Pi 3/4 probably works, but hasn't been tested yet.  
**Check that your hardware is not listed as "unsupported" here: https://www.home-assistant.io/integrations/bluetooth/**  

To check if your Bluetooth hardware is supported, run the following command on your system:
```bash
>$ hcitool dev
Devices:
	hci0	4C:79:6E:B2:0B:00
```
or
```
>$ bluetoothctl
[bluetooth]# list
  Controller 4C:79:6E:B2:0B:00 [default]
```
Your Bluetooth interface should be listed. If you have more than one, this component will use the first one or the one listed as default.

### Home Assistant installation
Any Home assistant installation should be supported: OS, Container, Core, Supervised.

If you run Home Assistant in a virtual machine, you have to connect your computer Bluetooth hardware to the VM:
- On VMWare: VM > Removable devices > (Your Bluetooth device i.e. Intel Wireless Bluetooth) > Connect
- On VirtualBox: Devices > USB devices > (Your Bluetooth device i.e. Intel Wireless Bluetooth)

## Setup instructions

### Automatic: add repository to HACS
1. Make sure [HACS](https://hacs.xyz/) is installed.  
2. Go to HACS > Frontend > Three dots > Custom repositories  
3. Add `https://github.com/rostyslav-khomyk/homeassistant-timebox-mini` as a custom repository (category: integration)  
4. Install "Timebox Mini service" that appeared in your Integrations tab  

### Manual: Copying into custom_components folder
Create a directory `custom_components` in your Home-Assistant configuration directory.
Copy the whole [custom_components/timebox_mini](custom_components/timebox_mini) folder from this project into the newly created directory `custom_components`.

The result of your copy action(s) should yield a directory structure like so:

```
homeassistant/
|-- custom_components/
|   |-- timebox_mini/
|       |-- animations/*.gif
|       |-- matrices/*.png
|       |-- __init__.py
|       |-- manifest.json
|       |-- services.yaml
```

### Enabling the custom_component
In order to enable this custom device_tracker component, add this code snippet to your Home-Assistant `configuration.yaml` file:

```yaml
timebox_mini:
```
After restart, the `timebox_mini.action` service will be available. You only need the MAC address of your Timebox.
![Timebox Mini Service](https://raw.githubusercontent.com/rostyslav-khomyk/homeassistant-timebox-mini/main/res/service.png)

When you run an action that changes what is displayed on the Timebox, an entity will be created to save the current displayed state.

![Timebox Mini entity](https://raw.githubusercontent.com/rostyslav-khomyk/homeassistant-timebox-mini/main/res/entity.png)

Please note that if you change the content on your Timebox without using the service (i.e. mobile app) this entity will not be updated.

### ESP32 Bluetooth Classic proxy

Timebox Mini uses Bluetooth Classic RFCOMM, so it cannot use Home Assistant's or ESPHome's standard BLE proxy. This fork can instead route the existing `timebox_mini.action` service through a compatible ESP32 TCP bridge.

Configure the integration with the proxy hostname, TCP port, and the Timebox Mini RFCOMM channel:

```yaml
timebox_mini:
  host: ble2hass.local
  port: 7777
  rfcomm_channel: 4
```

The service calls and automations remain unchanged. When `host` is omitted, the integration continues to use the Home Assistant host's local Bluetooth adapter directly.

### Moving text action
Use the `moving_text` action to render scrolling text with a generated pixel font:

```yaml
service: timebox_mini.action
data:
  mac_addr: "11:75:58:7B:8B:29"
  action: moving_text
  text: "DOOR OPEN"
  color: [255, 0, 0]
  background_color: [0, 0, 0]
  speed: 10
  repeat: 1
  direction: left
  sound: true
  sound_mode: 4
  sound_volume: 8
  sound_duration: 3
```

Moving text is streamed as individual 11x11 frames, so each service call displays only the text from that call.
The generated font uses full-height uppercase letters, shorter lowercase letters, and monochrome pixels for crisp display on the Timebox Mini matrix.
`speed: 10` is the fastest supported rate (one frame every 200 ms). The Timebox Mini cannot keep its sleep-sound mode and custom-image mode active simultaneously. When `sound` is enabled, the integration therefore plays and stops the built-in sound first, then streams the moving-text frames. The device briefly shows its built-in sleep image during the cue. Attention cues explicitly stop the sound without arming the sleep mode's device-shutdown timer.

The built-in sound can be tested independently:

```yaml
service: timebox_mini.action
data:
  mac_addr: "11:75:58:7B:8B:29"
  action: attention_sound
  sound_mode: 4
  sound_volume: 8
  sound_duration: 3
```

Sound modes are device-defined numeric slots; mode 4 is the verified default for Timebox Mini. The volume range is 0-15 and changes the Timebox Mini's global speaker volume.
`sound_duration` accepts 0.2-30 seconds. The integration stops the built-in sound explicitly when that duration expires and leaves the device-shutdown timer disabled.

The linked previews are room recordings made at device volume 15, not sound assets extracted from the Timebox. See the [capture notes and repeat estimates](docs/sounds/README.md). The interrupted capture did not produce trustworthy previews for every previously identified slot.

Observed Timebox Mini sound slots (device firmware may differ):

| Slot | Observed sound | Preview |
| ---: | --- | --- |
| 0 | No audible sound in the 30-second capture | — |
| 1 | No audible sound | — |
| 2 | Birds singing | [30.00 s](docs/sounds/slot-02-birds.m4a) |
| 3 | Ocean waves | [29.75 s](docs/sounds/slot-03-ocean-waves.m4a) |
| 4 | Pouring water | [30.00 s](docs/sounds/slot-04-pouring-water.m4a) |
| 5 | Mechanical music-box melody | [23.00 s](docs/sounds/slot-05-music-box.m4a) |
| 6 | No audible sound | — |
| 7 | Loud synthesized wave/chord | Not captured |
| 8 | Blowing wind | Not captured |
| 9 | Forest birds with an owl | Not captured |
| 10 | Many small birds chirping | Not captured |
| 11 | Flowing river | Not captured |
| 12 | Distant passenger-jet/steady engine sound | Not captured |
| 13 | Pleasant public-announcement chime | [4.50 s](docs/sounds/slot-13-announcement-chime.m4a) |
| 14 | Small group of birds | Not captured |
| 15 | Frogs | [19.00 s, partial](docs/sounds/slot-15-frogs.m4a) |
| 16 | Crib-mobile bedtime melody | [29.50 s](docs/sounds/slot-16-crib-mobile.m4a) |
| 17 | Wind through leaves | [18.75 s, partial](docs/sounds/slot-17-wind-through-leaves.m4a) |
| 18 | Underwater air bubbles | Not captured |

## Troubleshooting
If the actions are not applied to your Timebox when calling the service, you may need to pair manually with your device first using your OS Bluetooth settings or bluetoothctl:
```
[bluetooth]# list     
  --> Check that you have only one dongle listed
[bluetooth]# select [MAC address of your dongle]
[bluetooth]# power on
[bluetooth]# scan on
[bluetooth]# pair [your Timebox MAC address]
[bluetooth]# connect [your Timebox MAC address]
[bluetooth]# scan off
```
If calling the service still does not work, check  Home Assistant logs. If you have the following errors:
```
[custom_components.timebox_mini] Error connecting to 11:75:58:A6:00:00 : [Errno 16] Resource busy
[custom_components.timebox_mini] Error connecting to 11:75:58:A6:00:00 : [Errno 112] Host is down
```
you need to reset your dongle and pair with the Timebox again:
```
[bluetooth]# list     
  --> Check that you have only one dongle listed
[bluetooth]# select [MAC address of your dongle]
[bluetooth]# scan off
[bluetooth]# disconnect [your Timebox MAC address]
  --> ignore if error
[bluetooth]# remove [your Timebox MAC address]
  --> ignore if error
[bluetooth]# power off
  --> should display "Changing power off succeeded"
[bluetooth]# power on
[bluetooth]# scan on
[bluetooth]# pair [your Timebox MAC address]
[bluetooth]# connect [your Timebox MAC address]
[bluetooth]# scan off
```

## Create your own picture / animation
### Picture
You can create your own pixel-art matrix by using [PixilArt online tool](https://www.pixilart.com/draw).
- Start with a blank canvas of 11 x 11 
- Once finished, go to File > Download and download your .png

Copy the .png to the [matrices](custom_components/timebox_mini/matrices) folder and add its name to [services.yaml](custom_components/timebox_mini/services.yaml) in the `image` selector options. Restart HomeAssistant to take effect.

NOTE : the Timebox has a limited color set and cannot display all RGB shades, some color from your matrix will be approximated to the nearest one supported by Timebox.

### Animation
You can create a .gif for your animation using [EzGif Maker online tool](https://ezgif.com/maker). Start by loading all the matrices for your .gif that you have created previously (see above).

- Set the same delay for all frames. Timebox does not support different frame delays : if you want a frame to appear longer, duplicate it (use "copy" button).
- Min. delay is 200ms (`delay:20`), Timebox cannot display frames faster.
- Check `use global colormap`
- Click `Make a gif!` then click `Save` icon on the far right

Copy the .gif to the [animations](custom_components/timebox_mini/animations) folder and add its name to [services.yaml](custom_components/timebox_mini/services.yaml) in the `animation` selector options. Restart HomeAssistant to take effect.

## TODO
- Specify which bluetooth adapter to use (to have multiple Timebox, one per adapter)
- Weather info setting
