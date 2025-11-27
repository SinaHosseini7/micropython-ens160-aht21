# micropython-ens160-aht21

MicroPython driver for ENS160+AHT21 environmental sensor module on Raspberry Pi Pico

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![MicroPython](https://img.shields.io/badge/MicroPython-v1.20%2B-green.svg)
![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%20Pico%202%20(RP2350)-red.svg)
![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%20Pico%20(RP2040)-red.svg)
![Version](https://img.shields.io/badge/version-v1.0.0-orange.svg)
![GitHub stars](https://img.shields.io/github/stars/SinaHosseini7/micropython-ens160-aht21?style=social)
![GitHub forks](https://img.shields.io/github/forks/SinaHosseini7/micropython-ens160-aht21?style=social)

---

## Features

### ENS160 Air Quality Sensor
- UBA Air Quality Index (1-5 scale: Excellent to Unhealthy)
- TVOC measurement (0-65,000 ppb)
- eCO2 equivalent (400-65,000 ppm)
- Temperature/humidity compensation for improved accuracy
- Atomic burst-read for data consistency
- Automatic warm-up detection (3 minutes)
- Error recovery with automatic reset
- Optional firmware version reading
- Optional raw resistance data access

### AHT21 Temperature & Humidity Sensor
- High-precision temperature (-40°C to +80°C, ±0.3°C typical)
- High-precision humidity (0-100% RH, ±2% RH typical)
- CRC-8 data validation
- Automatic calibration on initialization
- Retry logic for transient errors
- Timeout protection

### Driver Quality
- Production-grade error handling with custom exceptions
- Thread-safety documentation for RP2350 dual-core usage
- Comprehensive docstrings with examples
- No external dependencies (uses standard MicroPython libraries only)

---

## Hardware Requirements

### Supported Platforms
- **Raspberry Pi Pico 2 (RP2350)** — Primary platform
- **Raspberry Pi Pico (RP2040)** — Fully compatible
- Any RP2040/RP2350-based board with I2C support

### Sensor Module
- **ENS160+AHT21 integrated module** (recommended)
- OR separate ENS160 and AHT21 sensors on same I2C bus

### I2C Configuration
- Any GPIO pins with I2C capability (examples use GP4=SDA, GP5=SCL)
- Frequency: 400 kHz recommended
- Pull-up resistors: 4.7kΩ on SDA/SCL (usually built-in on breakout boards)

### Power Supply
- Voltage: 3.3V (both sensors)
- Decoupling capacitors recommended: 100nF + 10µF near sensors

### I2C Addresses
| Sensor | Address | Notes |
|--------|---------|-------|
| ENS160 | 0x53 | Default (ADDR pin high on module) |
| AHT21 | 0x38 | Fixed address |

---

## Wiring Diagram

```
Raspberry Pi Pico         ENS160+AHT21 Module
─────────────────         ──────────────────
3V3 (Pin 36)        →     VDD / 3.3V
GND (Pin 38)        →     GND
GP4 (Pin 6)         →     SDA
GP5 (Pin 7)         →     SCL
```

> **Note:** Any GPIO pins can be used for I2C. Adjust the `Pin()` numbers in your code accordingly.

---

## Installation

### Step 1: Ensure MicroPython is Installed
Install MicroPython v1.20+ on your Raspberry Pi Pico. Download from [micropython.org](https://micropython.org/download/RPI_PICO/).

### Step 2: Download the Repository
```bash
git clone https://github.com/SinaHosseini7/micropython-ens160-aht21.git
```

### Step 3: Copy Driver Files to Your Pico
Copy these files to your Pico's root directory:
- `ens160.py` (required)
- `aht21.py` (required)
- `example.py` (optional, for testing)

**Methods to copy files:**
- **Thonny IDE:** File → Save As → MicroPython device
- **mpremote:** `mpremote cp ens160.py :ens160.py`
- **ampy:** `ampy put ens160.py`

---

## Quick Start

```python
from machine import I2C, Pin
import time
from ens160 import ENS160
from aht21 import AHT21

# Initialize I2C (adjust pins as needed)
i2c = I2C(0, scl=Pin(5), sda=Pin(4), freq=400_000)

# Initialize sensors
aht = AHT21(i2c)
ens = ENS160(i2c)

# Main loop
while True:
    # Read temperature and humidity
    temp, hum = aht.read_temperature_humidity()
    
    # Apply compensation for better accuracy
    ens.set_compensation(temp, hum)
    
    # Update and read air quality
    if ens.update():
        print(f"Temperature: {temp:.1f}°C")
        print(f"Humidity: {hum:.1f}%RH")
        print(f"AQI: {ens.aqi} ({ens.AQI_RATINGS[ens.aqi]})")
        print(f"TVOC: {ens.tvoc}ppb")
        print(f"eCO2: {ens.eco2}ppm")
        print("-" * 30)
    else:
        print(f"Sensor status: {ens.status}")
    
    time.sleep(2)
```

---

## API Reference

### ENS160 Class

#### Constructor

```python
ENS160(i2c, address=0x53)
```
Initialize the ENS160 sensor with PART_ID verification.

**Parameters:**
- `i2c` — Configured I2C bus object
- `address` — I2C address (default: 0x53)

**Raises:**
- `ENS160InitError` — Initialization or PART_ID verification failure

---

#### Methods

**`set_compensation(temperature_c, humidity_rh)`**

Set temperature/humidity compensation for improved accuracy.

```python
ens.set_compensation(25.0, 50.0)
```
- `temperature_c` — Temperature in Celsius (-40 to 85°C, auto-clipped)
- `humidity_rh` — Relative humidity in % (0 to 100%, auto-clipped)

> **Tip:** Call before each `update()` for best results.

---

**`update() -> bool`**

Read and cache sensor data atomically.

```python
if ens.update():
    print(f"AQI: {ens.aqi}")
```

**Returns:** `True` if valid data available, `False` if warming up or no new data.

---

**`reset()`**

Soft reset and restore to STANDARD mode. Automatically called on error states.

---

**`get_firmware_version() -> str`**

Get firmware version string (e.g., "1.2.3").

```python
version = ens.get_firmware_version()
```

---

**`get_raw_resistance(sensor_num) -> int`**

Get raw resistance value for advanced gas detection.

```python
raw_r1 = ens.get_raw_resistance(1)  # sensor_num: 1 or 4
resistance_ohms = 2 ** (raw_r1 / 2048)
```

---

#### Properties (Read-Only)

| Property | Type | Description |
|----------|------|-------------|
| `aqi` | int | Air Quality Index (1-5, UBA scale) |
| `tvoc` | int | Total VOC in ppb (0-65,000) |
| `eco2` | int | Equivalent CO2 in ppm (400-65,000) |
| `status` | str | Current status: "OK", "Warm-up", "Initial Startup", or "Error" |
| `warming_up` | bool | True if in 3-minute warm-up phase |

#### Class Attribute

```python
ENS160.AQI_RATINGS = {
    1: "Excellent",
    2: "Good", 
    3: "Moderate",
    4: "Poor",
    5: "Unhealthy"
}
```

#### Exceptions

| Exception | Description |
|-----------|-------------|
| `ENS160Error` | Base exception for all ENS160 errors |
| `ENS160InitError` | Initialization or PART_ID verification failure |
| `ENS160CommunicationError` | I2C communication error |
| `ENS160DataError` | Invalid data or validity flag error |

---

### AHT21 Class

#### Constructor

```python
AHT21(i2c, address=0x38)
```
Initialize and auto-calibrate the AHT21 sensor.

**Parameters:**
- `i2c` — Configured I2C bus object  
- `address` — I2C address (default: 0x38)

**Raises:**
- `AHT21CalibrationError` — If calibration fails after 3 attempts

---

#### Methods

**`read_temperature_humidity(retries=3) -> tuple`**

Read temperature and humidity with automatic retry on errors.

```python
temp, hum = aht.read_temperature_humidity()
print(f"{temp:.1f}°C, {hum:.1f}%RH")
```

**Returns:** Tuple of `(temperature_celsius, humidity_percent)`

---

#### Exceptions

| Exception | Description |
|-----------|-------------|
| `AHT21Error` | Base exception for all AHT21 errors |
| `AHT21CalibrationError` | Calibration failure after retries |
| `AHT21CRCError` | Data corruption detected (CRC mismatch) |
| `AHT21TimeoutError` | Sensor timeout |

---

## Important Notes

### ENS160 Calibration and Warm-up

⚠️ **First-time use:** The ENS160 requires **24 hours of continuous power** for baseline calibration to persist in EEPROM.

⚠️ **Every power-on:** A **3-minute warm-up period** is required before valid readings. The driver automatically detects this state.

⚠️ **Status monitoring:** Use the `ens.status` property to check the sensor state:
- `"OK"` — Normal operation, data is valid
- `"Warm-up"` — 3-minute warm-up in progress
- `"Initial Startup"` — First-time calibration (24h)
- `"Error"` — Recoverable error (auto-reset triggered)

### Temperature/Humidity Compensation

Providing temperature and humidity compensation **significantly improves** ENS160 accuracy. Always call `set_compensation()` before each `update()`:

```python
temp, hum = aht.read_temperature_humidity()
ens.set_compensation(temp, hum)
ens.update()
```

Without compensation, the sensor assumes 25°C and 50% RH.

### Thread Safety (RP2350 Dual-Core)

The drivers are **NOT thread-safe** by default. For multi-core applications on the RP2350, protect sensor access with a lock:

```python
import _thread

sensor_lock = _thread.allocate_lock()

with sensor_lock:
    temp, hum = aht.read_temperature_humidity()
    ens.set_compensation(temp, hum)
    ens.update()
```

### I2C Pin Configuration

The examples use GP4 (SDA) and GP5 (SCL), but any GPIO pins with I2C capability can be used. Update the `Pin()` numbers in your code as needed.

---

## Advanced Usage Examples

### Error Handling

```python
from machine import I2C, Pin
from ens160 import ENS160, ENS160Error, ENS160InitError
from aht21 import AHT21, AHT21Error, AHT21CalibrationError

try:
    i2c = I2C(0, scl=Pin(5), sda=Pin(4), freq=400_000)
    aht = AHT21(i2c)
    ens = ENS160(i2c)
except ENS160InitError as e:
    print(f"ENS160 initialization failed: {e}")
except AHT21CalibrationError as e:
    print(f"AHT21 calibration failed: {e}")
except OSError as e:
    print(f"I2C communication error: {e}")
```

### Dual-Core Usage (RP2350)

```python
import _thread
import time
from machine import I2C, Pin
from ens160 import ENS160
from aht21 import AHT21

i2c = I2C(0, scl=Pin(5), sda=Pin(4), freq=400_000)
aht = AHT21(i2c)
ens = ENS160(i2c)

sensor_lock = _thread.allocate_lock()

def core1_task():
    while True:
        with sensor_lock:
            temp, hum = aht.read_temperature_humidity()
            ens.set_compensation(temp, hum)
            if ens.update():
                print(f"Core1: AQI={ens.aqi}, TVOC={ens.tvoc}ppb")
        time.sleep(2)

_thread.start_new_thread(core1_task, ())
```

### Advanced Air Quality Monitoring

```python
# Get firmware version
try:
    version = ens.get_firmware_version()
    print(f"ENS160 Firmware: {version}")
except:
    print("Firmware version unavailable")

# Read raw resistance for advanced gas detection
raw_r1 = ens.get_raw_resistance(1)
resistance_ohms = 2 ** (raw_r1 / 2048)
print(f"Sensor 1 Resistance: {resistance_ohms:.0f}Ω")

# Air quality thresholds
if ens.update():
    if ens.aqi >= 4:
        print("⚠ Poor air quality - ventilation recommended!")
    if ens.eco2 > 1000:
        print("⚠ High CO2 levels detected!")
```

---

## Troubleshooting

| Problem | Possible Cause | Solution |
|---------|---------------|----------|
| `ENS160InitError: Invalid PART_ID` | Wrong I2C address or wiring | Verify ENS160 address is 0x53, check SDA/SCL connections |
| `AHT21CalibrationError` | Power supply issue or bad sensor | Check 3.3V power, ensure pull-up resistors present |
| `OSError: [Errno 5] EIO` | I2C communication failure | Check wiring, verify pull-up resistors (4.7kΩ), reduce I2C frequency to 100kHz |
| `AHT21CRCError` | Data corruption | Check for electrical noise, shorten wires, add decoupling capacitors |
| ENS160 shows "Warm-up" for >3 min | First-time use or power interruption | Wait 24 hours with continuous power for initial calibration |
| Inaccurate ENS160 readings | Missing compensation | Always call `set_compensation()` before `update()` |
| I2C address conflict | Multiple sensors on bus | Verify each sensor has unique address (ENS160=0x53, AHT21=0x38) |
| RP2350 multi-core crashes | Race condition | Wrap sensor access with `_thread.allocate_lock()` |
| No I2C devices found | Wiring issue | Run `i2c.scan()` to check connected devices |

---

## File Structure

```
your-project/
├── ens160.py          # ENS160 driver (required)
├── aht21.py           # AHT21 driver (required)
├── example.py         # Usage example
├── LICENSE            # MIT License
└── README.md          # This file
```

---

## Technical Specifications

### ENS160 Specifications

| Parameter | Range | Resolution | Notes |
|-----------|-------|------------|-------|
| TVOC | 0 - 65,000 ppb | 1 ppb | Total Volatile Organic Compounds |
| eCO2 | 400 - 65,000 ppm | 1 ppm | Equivalent CO2 |
| AQI-UBA | 1 - 5 | 1 | German Federal Environmental Agency standard |
| Supply Voltage | 1.71 - 1.98V | — | Onboard regulator handles 3.3V input |
| I2C Clock | Up to 400 kHz | — | Fast mode recommended |
| Warm-up Time | 3 minutes | — | After every power-on |
| Initial Calibration | 24 hours | — | First-time use only |

### AHT21 Specifications

| Parameter | Range | Accuracy | Resolution |
|-----------|-------|----------|------------|
| Temperature | -40°C to +80°C | ±0.3°C (typical) | 0.01°C |
| Humidity | 0% to 100% RH | ±2% RH (typical) | 0.024% RH |
| Supply Voltage | 2.2V - 5.5V | — | 3.3V typical |
| I2C Address | 0x38 | — | Fixed |
| Measurement Time | ~80ms | — | Maximum 1 Hz sampling |

---

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Guidelines
- Follow the existing code style
- Add tests for new features
- Update documentation as needed
- Ensure all tests pass before submitting

### Reporting Issues
- Use GitHub Issues for bug reports and feature requests
- Include MicroPython version and hardware details
- Provide minimal code to reproduce the issue

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- ScioSense for the ENS160 sensor and comprehensive datasheet
- Aosong Electronics for the AHT21 sensor
- MicroPython community for the excellent embedded Python implementation
- Many thanks to Claude Opus 4.5 for help in debugging the code and optimizing it.

---

## References

### Datasheets
- [ENS160 Official Datasheet](https://www.sciosense.com/wp-content/uploads/2023/12/ENS160-Datasheet.pdf)
- [AHT21 Official Datasheet](https://www.aosong.com/userfiles/files/media/Data%20Sheet%20AHT21.pdf)

### Where to Buy
- [DFRobot: Gravity ENS160 Air Quality Sensor](https://www.dfrobot.com/product-2526.html)
- [Adafruit: ENS160 MOX Gas Sensor](https://www.adafruit.com/product/5606)
- [SparkFun: Indoor Air Quality Sensor - ENS160](https://www.sparkfun.com/products/20844)
- Search for: "ENS160+AHT21 module" on electronics suppliers

### Related Resources
- [MicroPython Official Documentation](https://docs.micropython.org/)
- [Raspberry Pi Pico Documentation](https://www.raspberrypi.com/documentation/microcontrollers/)
- [MicroPython Forum](https://forum.micropython.org/)

---

## Author

**GitHub:** [@SinaHosseini7](https://github.com/SinaHosseini7)

If you find this project helpful, please consider giving it a ⭐ on GitHub!
