"""
ENS160 MicroPython Driver for Raspberry Pi Pico 2

Digital Metal-Oxide Multi-Gas Sensor for Air Quality Monitoring

Features:
    - UBA Air Quality Index (1-5 scale)
    - TVOC measurement (0-65000 ppb)
    - eCO2 equivalent (400-65000 ppm)
    - Temperature/humidity compensation
    - Atomic burst-read for data consistency
    
Hardware Requirements:
    - I2C bus configured (GP4=SDA, GP5=SCL, 400kHz)
    - 3.3V supply with 100nF + 10µF decoupling capacitors
    - 4.7kΩ pull-ups on SDA/SCL
    - ENS160 I2C address: 0x53 (ADDR pin high on module)

Threading Notes (RP2350 Dual-Core):
    This driver is NOT thread-safe. If using on RP2350's second core,
    wrap all sensor operations with a lock:
    
    import _thread
    sensor_lock = _thread.allocate_lock()
    
    with sensor_lock:
        ens.update()
        data = (ens.aqi, ens.tvoc, ens.eco2)

Basic Usage:
    from machine import I2C, Pin
    import time
    from ens160 import ENS160
    from aht21 import AHT21
    
    i2c = I2C(0, scl=Pin(5), sda=Pin(4), freq=400_000)
    aht = AHT21(i2c)
    ens = ENS160(i2c)
    
    while True:
        temp, hum = aht.read_temperature_humidity()
        ens.set_compensation(temp, hum)
        if ens.update():
            print(f"AQI: {ens.aqi}, TVOC: {ens.tvoc}ppb, eCO2: {ens.eco2}ppm")
        time.sleep(2)
"""

import time
import struct
from machine import I2C
from micropython import const

# === CONSTANTS (All from ENS160 datasheet) ===

# Device Identification
_REG_PART_ID = const(0x00)       # 2 bytes, must read 0x0160 (LE)

# Configuration  
_REG_OPMODE = const(0x10)        # Operating mode
_REG_CONFIG = const(0x11)        # Interrupt config (not used)
_REG_COMMAND = const(0x12)       # System commands

# Compensation Inputs (16-bit Little-Endian)
_REG_TEMP_IN = const(0x13)       # Temperature: (°C + 273.15) × 64
_REG_RH_IN = const(0x15)         # Humidity: %RH × 512

# Data Outputs (Burst Read: 0x20-0x25, 6 bytes)
_REG_DEVICE_STATUS = const(0x20) # Status byte
_REG_DATA_AQI = const(0x21)      # AQI (1-5)
_REG_DATA_TVOC = const(0x22)     # TVOC in ppb (16-bit LE)
_REG_DATA_ECO2 = const(0x24)     # eCO2 in ppm (16-bit LE)

# General Purpose (Optional Feature)
_REG_GPR_READ = const(0x48)      # 8 bytes, for firmware version + raw data

# Operating Modes
_OPMODE_DEEP_SLEEP = const(0x00)
_OPMODE_IDLE = const(0x01)
_OPMODE_STANDARD = const(0x02)   # Active sensing mode
_OPMODE_RESET = const(0xF0)

# Commands
_CMD_GET_APPVER = const(0x0E)
_CMD_CLRGPR = const(0xCC)

# Timing (milliseconds) - Datasheet Table 9
_TIMING_RESET = const(20)        # CRITICAL: Must wait 20ms after reset!
_TIMING_MODE_SWITCH = const(10)

# === EXCEPTIONS ===
class ENS160Error(Exception):
    """Base exception for all ENS160 errors."""
    pass

class ENS160InitError(ENS160Error):
    """Sensor initialization or PART_ID verification failed."""
    pass

class ENS160CommunicationError(ENS160Error):
    """I2C communication failure."""
    pass

class ENS160DataError(ENS160Error):
    """Invalid data or validity flag error."""
    pass


class ENS160:
    """
    MicroPython driver for ENS160 Digital Air Quality Sensor.
    
    Features:
    - Atomic burst-read for data consistency
    - Temperature/humidity compensation (use with AHT21)
    - Automatic warm-up detection (3 minutes)
    - UBA Air Quality Index (1-5 scale)
    
    Important:
    - First use requires 24h continuous power for calibration persistence
    - After calibration, 3-minute warm-up needed after power-on
    - NOT thread-safe (see module docstring for RP2350 dual-core usage)
    
    Example:
        >>> i2c = I2C(0, scl=Pin(5), sda=Pin(4), freq=400_000)
        >>> aht = AHT21(i2c)
        >>> ens = ENS160(i2c)
        >>> 
        >>> temp, hum = aht.read_temperature_humidity()
        >>> ens.set_compensation(temp, hum)
        >>> if ens.update():
        ...     print(f"AQI: {ens.aqi}, TVOC: {ens.tvoc}ppb")
    """
    
    # AQI Rating Lookup (Datasheet Table 6)
    AQI_RATINGS = {
        1: "Excellent",  # 0-65 ppb
        2: "Good",       # 65-220 ppb
        3: "Moderate",   # 220-660 ppb
        4: "Poor",       # 660-2200 ppb
        5: "Unhealthy"   # 2200+ ppb
    }
    
    def __init__(self, i2c: I2C, address: int = 0x53) -> None:
        """
        Initialize ENS160 sensor.
        
        Performs:
        1. PART_ID verification (must be 0x0160)
        2. Soft reset (20ms wait - CRITICAL)
        3. Mode: RESET → IDLE → STANDARD
        4. Default compensation (25°C, 50%RH)
        5. Cache initialization
        
        Args:
            i2c: Configured I2C bus (400kHz recommended)
            address: I2C address (0x53 for ENS160+AHT21 module)
        
        Raises:
            ENS160InitError: PART_ID mismatch or communication failure
        
        Example:
            i2c = I2C(0, scl=Pin(5), sda=Pin(4), freq=400_000)
            sensor = ENS160(i2c)  # Auto-initializes
        """
        self._i2c = i2c
        self._address = address
        
        # Initialize cache
        self._aqi = 0
        self._tvoc = 0
        self._eco2 = 400
        self._validity_flag = 1
        
        # Step 1: Read and verify PART_ID (should be 0x0160)
        try:
            part_id_bytes = self._read_registers(_REG_PART_ID, 2)
            part_id = struct.unpack('<H', part_id_bytes)[0]
            
            if part_id != 0x0160:
                raise ENS160InitError(
                    f"Invalid PART_ID: expected 0x0160, got 0x{part_id:04X}. "
                    "Check wiring (SDA=GP4, SCL=GP5) and I2C address (should be 0x53)."
                )
        except OSError as e:
            raise ENS160InitError(
                f"Failed to communicate with ENS160 at address 0x{address:02X}: {e}. "
                "Check I2C connections and power supply."
            )
        
        # Step 2: Perform soft reset
        self._write_register(_REG_OPMODE, _OPMODE_RESET)
        time.sleep_ms(_TIMING_RESET)  # CRITICAL: Must wait 20ms!
        
        # Step 3: Switch to IDLE mode
        self._write_register(_REG_OPMODE, _OPMODE_IDLE)
        time.sleep_ms(_TIMING_MODE_SWITCH)
        
        # Step 4: Set default compensation (25°C, 50%RH)
        self.set_compensation(25.0, 50.0)
        
        # Step 5: Switch to STANDARD mode (active sensing)
        self._write_register(_REG_OPMODE, _OPMODE_STANDARD)
        time.sleep_ms(_TIMING_MODE_SWITCH)

    def set_compensation(self, temperature_c: float, humidity_rh: float) -> None:
        """
        Set temperature/humidity compensation for accuracy improvement.
        
        Formulas:
        - Temperature: (T_celsius + 273.15) × 64 → 16-bit LE
        - Humidity: RH_% × 512 → 16-bit LE
        
        Args:
            temperature_c: -40 to 85°C (auto-clipped)
            humidity_rh: 0 to 100% (auto-clipped)
        
        Note: Call before each update() for best accuracy
        
        Example:
            temp, hum = aht.read_temperature_humidity()
            ens.set_compensation(temp, hum)
            ens.update()
        """
        # Clip to valid ranges (defensive programming)
        temperature_c = max(-40.0, min(85.0, temperature_c))
        humidity_rh = max(0.0, min(100.0, humidity_rh))
        
        # Calculate compensation values (Datasheet Section 16.2.5 & 16.2.6)
        # Temperature: (°C + 273.15) × 64
        # Test case: 25°C → (25 + 273.15) × 64 = 19081 = 0x4A89
        temp_value = int((temperature_c + 273.15) * 64)
        
        # Humidity: %RH × 512
        # Test case: 50%RH → 50 × 512 = 25600 = 0x6400
        rh_value = int(humidity_rh * 512)
        
        # Write to compensation registers
        self._write_register_16(_REG_TEMP_IN, temp_value)
        self._write_register_16(_REG_RH_IN, rh_value)

    def update(self) -> bool:
        """
        Read and cache sensor data atomically.
        
        Process:
        1. Check NEWDAT flag (bit 1 of status byte)
        2. Burst read 6 bytes (0x20-0x25)
        3. Parse and cache: validity_flag, AQI, TVOC, eCO2
        4. Return True if data valid (validity_flag == 0)
        
        Returns:
            bool: True if data valid, False if warming up or no new data
        
        Validity States (Datasheet Table 10):
            0: Normal operation (return True)
            1: Warm-up (3 min after power-on)
            2: Initial startup (first hour, first-time use only)
            3: Error (auto-reset and retry)
        
        Example:
            if ens.update():
                print(f"Valid data: AQI={ens.aqi}")
            else:
                print(f"Status: {ens.status}")
        """
        # Step 1: Check NEWDAT flag (bit 1)
        status_byte = self._read_register(_REG_DEVICE_STATUS)
        if not (status_byte & 0x02):
            return False  # No new data available
        
        # Step 2: Burst read 6 bytes (ATOMIC operation - critical!)
        # Registers 0x20-0x25: STATUS, AQI, TVOC_L, TVOC_H, ECO2_L, ECO2_H
        data = self._read_registers(_REG_DEVICE_STATUS, 6)
        
        # Step 3: Parse data (Datasheet Table 26)
        # Status byte (0x20): bits 2-3 are validity flag
        self._validity_flag = (data[0] >> 2) & 0x03
        
        # AQI byte (0x21): bits 0-2 only (1-5 scale)
        self._aqi = data[1] & 0x07
        
        # TVOC (0x22-0x23): 16-bit little-endian, ppb
        self._tvoc = struct.unpack('<H', data[2:4])[0]
        
        # eCO2 (0x24-0x25): 16-bit little-endian, ppm
        self._eco2 = struct.unpack('<H', data[4:6])[0]
        
        # Step 4: Handle validity states
        if self._validity_flag == 3:  # Error state
            # AUTO-RECOVERY: Reset and retry once
            self.reset()
            time.sleep_ms(200)  # Allow reset to complete
            # Recursive retry (only once due to reset clearing error)
            return self.update()
        
        # Return True only if normal operation (validity_flag == 0)
        return (self._validity_flag == 0)

    @property
    def aqi(self) -> int:
        """Air Quality Index (1-5, UBA scale). Call update() first."""
        return self._aqi

    @property
    def tvoc(self) -> int:
        """TVOC in ppb (0-65000). Call update() first."""
        return self._tvoc

    @property
    def eco2(self) -> int:
        """Equivalent CO2 in ppm (400-65000). Call update() first."""
        return self._eco2

    @property
    def status(self) -> str:
        """Current status: 'OK', 'Warm-up', 'Initial Startup', or 'Error'."""
        status_map = {
            0: "OK", 
            1: "Warm-up",          # 3-minute warm-up
            2: "Initial Startup",   # First hour, first-time use
            3: "Error"             # Recoverable error
        }
        return status_map.get(self._validity_flag, "Unknown")

    @property
    def warming_up(self) -> bool:
        """True if in 3-minute warm-up phase."""
        return (self._validity_flag == 1)

    def reset(self) -> None:
        """
        Soft reset and restore to STANDARD mode.
        Automatically restores operation after error states.
        """
        # Send reset command
        self._write_register(_REG_OPMODE, _OPMODE_RESET)
        time.sleep_ms(_TIMING_RESET)  # 20ms - CRITICAL!
        
        # Transition through IDLE
        self._write_register(_REG_OPMODE, _OPMODE_IDLE)
        time.sleep_ms(_TIMING_MODE_SWITCH)
        
        # Restore default compensation
        self.set_compensation(25.0, 50.0)
        
        # Back to STANDARD mode
        self._write_register(_REG_OPMODE, _OPMODE_STANDARD)
        time.sleep_ms(_TIMING_MODE_SWITCH)
        
        # Reset cache to defaults
        self._aqi = 0
        self._tvoc = 0
        self._eco2 = 400
        self._validity_flag = 1

    def get_firmware_version(self) -> str:
        """
        Get firmware version (major.minor.release).
        Requires mode switch to IDLE.
        
        Returns:
            str: Firmware version string (e.g., "1.2.3")
        
        Example:
            version = ens.get_firmware_version()
            print(f"Firmware: {version}")
        """
        # Save current mode
        current_mode = _OPMODE_STANDARD
        
        try:
            # Switch to IDLE mode (required for command)
            self._write_register(_REG_OPMODE, _OPMODE_IDLE)
            time.sleep_ms(_TIMING_MODE_SWITCH)
            
            # Send GET_APPVER command
            self._write_register(_REG_COMMAND, _CMD_GET_APPVER)
            time.sleep_ms(10)  # Command processing
            
            # Read GPR registers (8 bytes)
            # Version is at GPR_READ[4:6]
            gpr_data = self._read_registers(_REG_GPR_READ, 8)
            
            major = gpr_data[4]
            minor = gpr_data[5]
            release = gpr_data[6]
            
            return f"{major}.{minor}.{release}"
            
        finally:
            # Restore previous mode
            self._write_register(_REG_OPMODE, current_mode)
            time.sleep_ms(_TIMING_MODE_SWITCH)

    def get_raw_resistance(self, sensor_num: int) -> int:
        """
        Get raw resistance value for advanced gas detection.
        
        Args:
            sensor_num: 1 or 4 (only these sensors expose raw data)
        
        Returns:
            int: Raw value (0-65535), needs conversion: R_res[Ω] = 2^(raw/2048)
        
        Note: Requires reading GPR_READ registers. See Datasheet Section 7.
        
        Example:
            raw_r1 = ens.get_raw_resistance(1)
            resistance_ohms = 2 ** (raw_r1 / 2048)
        """
        if sensor_num not in (1, 4):
            raise ValueError("sensor_num must be 1 or 4")
        
        # Read GPR_READ registers (8 bytes)
        gpr_data = self._read_registers(_REG_GPR_READ, 8)
        
        if sensor_num == 1:
            # R1_raw at bytes 0-1 (little-endian)
            return struct.unpack('<H', gpr_data[0:2])[0]
        else:  # sensor_num == 4
            # R4_raw at bytes 6-7 (little-endian)
            return struct.unpack('<H', gpr_data[6:8])[0]

    # === Private Helper Methods (match aht21.py style) ===

    def _read_register(self, reg: int) -> int:
        """Read single byte with retry."""
        try:
            return self._i2c.readfrom_mem(self._address, reg, 1)[0]
        except OSError:
            time.sleep_ms(10)
            try:
                return self._i2c.readfrom_mem(self._address, reg, 1)[0]
            except OSError as e:
                raise ENS160CommunicationError(f"Failed to read register 0x{reg:02X}: {e}")

    def _read_registers(self, reg: int, count: int) -> bytes:
        """Read multiple bytes with retry."""
        try:
            return self._i2c.readfrom_mem(self._address, reg, count)
        except OSError:
            time.sleep_ms(10)
            try:
                return self._i2c.readfrom_mem(self._address, reg, count)
            except OSError as e:
                raise ENS160CommunicationError(f"Failed to read {count} bytes from 0x{reg:02X}: {e}")

    def _write_register(self, reg: int, value: int) -> None:
        """Write single byte with retry."""
        try:
            self._i2c.writeto_mem(self._address, reg, bytes([value]))
        except OSError:
            time.sleep_ms(10)
            try:
                self._i2c.writeto_mem(self._address, reg, bytes([value]))
            except OSError as e:
                raise ENS160CommunicationError(f"Failed to write 0x{value:02X} to register 0x{reg:02X}: {e}")

    def _write_register_16(self, reg: int, value: int) -> None:
        """Write 16-bit little-endian value with retry."""
        data = struct.pack('<H', value)
        try:
            self._i2c.writeto_mem(self._address, reg, data)
        except OSError:
            time.sleep_ms(10)
            try:
                self._i2c.writeto_mem(self._address, reg, data)
            except OSError as e:
                raise ENS160CommunicationError(f"Failed to write 0x{value:04X} to register 0x{reg:02X}: {e}")
