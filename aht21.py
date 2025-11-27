"""
AHT21 MicroPython Driver for Raspberry Pi Pico 2

Hardware Requirements:
    - I2C bus configured (GP4=SDA, GP5=SCL, 400kHz)
    - 3.3V supply with 10µF decoupling capacitor
    - 4.7kΩ pull-ups on SDA/SCL

Basic Usage:
    from machine import I2C, Pin
    import time
    from aht21 import AHT21
    
    i2c = I2C(0, scl=Pin(5), sda=Pin(4), freq=400_000)
    sensor = AHT21(i2c)
    
    temp, hum = sensor.read_temperature_humidity()
    print(f"{temp:.1f}°C, {hum:.1f}%RH")
"""

import time
from machine import I2C

# === CONSTANTS (All from datasheet) ===
AHT21_I2C_ADDR = 0x38

# Commands
AHT21_CMD_STATUS = 0x71
AHT21_CMD_SOFTRESET = 0xBA
AHT21_CMD_INITIALIZE = 0xBE
AHT21_CMD_TRIGGER = 0xAC

# Status Masks
AHT21_STATUS_BUSY = 0x80        # Bit 7
AHT21_STATUS_CALIBRATED = 0x18  # Bits 3 & 4 (both required)

# CRC
AHT21_CRC_POLYNOMIAL = 0x31
AHT21_CRC_INIT = 0xFF

# Timing (milliseconds)
AHT21_POWERUP_DELAY = 100
AHT21_SOFTRESET_DELAY = 20
AHT21_INIT_DELAY = 10
AHT21_MEASUREMENT_DELAY = 80
AHT21_BUSY_TIMEOUT = 150

# === EXCEPTIONS ===
class AHT21Error(Exception):
    """Base exception for all AHT21 errors."""
    pass

class AHT21CalibrationError(AHT21Error):
    """Sensor failed to calibrate after retries."""
    pass

class AHT21CRCError(AHT21Error):
    """Data corruption detected (CRC mismatch)."""
    pass

class AHT21TimeoutError(AHT21Error):
    """Sensor remained busy beyond timeout."""
    pass


class AHT21:
    def __init__(self, i2c: I2C, address: int = 0x38):
        """
        Initialize AHT21 sensor with automatic calibration.
        
        Args:
            i2c: Configured I2C bus object
            address: I2C address (default 0x38)
        
        Raises:
            AHT21CalibrationError: If calibration fails after 3 attempts
            OSError: If I2C communication fails
        
        Example:
            i2c = I2C(0, scl=Pin(5), sda=Pin(4), freq=400_000)
            sensor = AHT21(i2c)  # Auto-calibrates
        """
        self._i2c = i2c
        self._address = address
        
        # Power-on stability
        time.sleep_ms(AHT21_POWERUP_DELAY)
        
        # Soft reset
        self._i2c.writeto(self._address, bytes([AHT21_CMD_SOFTRESET]))
        time.sleep_ms(AHT21_SOFTRESET_DELAY)
        
        # Calibration loop (max 3 attempts)
        for attempt in range(3):
            if self._is_calibrated():
                return  # Success
            
            # Send initialization command
            self._i2c.writeto(
                self._address,
                bytes([AHT21_CMD_INITIALIZE, 0x08, 0x00])
            )
            time.sleep_ms(AHT21_INIT_DELAY)
        
        # All attempts failed
        raise AHT21CalibrationError(
            "Sensor failed to calibrate after 3 attempts. "
            "Check wiring and power supply."
        )

    def read_temperature_humidity(self, retries: int = 3) -> tuple:
        """
        Read temperature and humidity with automatic retry on errors.
        
        Args:
            retries: Number of retry attempts on CRC/timeout errors (default 3)
        
        Returns:
            Tuple of (temperature_celsius: float, humidity_percent: float)
        
        Raises:
            AHT21CRCError: Data corruption detected after all retries
            AHT21TimeoutError: Sensor timeout after all retries
            OSError: I2C communication failure
        
        Example:
            try:
                temp, hum = sensor.read_temperature_humidity()
                print(f"{temp:.1f}°C, {hum:.1f}%RH")
            except AHT21Error as e:
                print(f"Sensor error: {e}")
        """
        for attempt in range(retries):
            try:
                # 1. Trigger measurement
                self._i2c.writeto(
                    self._address,
                    bytes([AHT21_CMD_TRIGGER, 0x33, 0x00])
                )
                
                # 2. Wait for conversion (typical time)
                time.sleep_ms(AHT21_MEASUREMENT_DELAY)
                
                # 3. Poll busy flag (with timeout protection)
                start_time = time.ticks_ms()
                while self._is_busy():
                    if time.ticks_diff(time.ticks_ms(), start_time) > AHT21_BUSY_TIMEOUT:
                        raise AHT21TimeoutError(
                            f"Sensor timeout after {AHT21_BUSY_TIMEOUT}ms"
                        )
                    time.sleep_ms(5)  # Poll every 5ms
                
                # 4. Read 7 bytes (status + data + CRC)
                data = self._i2c.readfrom(self._address, 7)
                
                # 5. Validate CRC
                calculated_crc = self._calculate_crc8(data[0:6])
                if calculated_crc != data[6]:
                    raise AHT21CRCError(
                        f"CRC mismatch: calculated=0x{calculated_crc:02X}, "
                        f"received=0x{data[6]:02X}"
                    )
                
                # 6. Extract 20-bit raw values
                raw_humidity = (data[1] << 12) | (data[2] << 4) | (data[3] >> 4)
                raw_temperature = ((data[3] & 0x0F) << 16) | (data[4] << 8) | data[5]
                
                # 7. Convert to physical units
                humidity = (raw_humidity / 1048576.0) * 100.0
                temperature = (raw_temperature / 1048576.0) * 200.0 - 50.0
                
                return (temperature, humidity)
            
            except (AHT21CRCError, AHT21TimeoutError) as e:
                if attempt == retries - 1:
                    raise  # Last attempt failed
                time.sleep_ms(50)  # Brief delay before retry

    def _read_status(self) -> int:
        """
        Read status byte (command 0x71).
        
        Returns:
            Status byte containing busy/calibration flags
        """
        self._i2c.writeto(self._address, bytes([AHT21_CMD_STATUS]))
        return self._i2c.readfrom(self._address, 1)[0]

    def _is_busy(self) -> bool:
        """
        Check if sensor is performing measurement.
        
        Returns:
            True if busy (bit 7 set), False if idle
        """
        status = self._read_status()
        return (status & AHT21_STATUS_BUSY) != 0

    def _is_calibrated(self) -> bool:
        """
        Check calibration status per datasheet Section 7.4.
        
        Datasheet requirement: "If the status word and 0x18 
        are not equal to 0x18" → sensor is uncalibrated
        
        Returns:
            True if both calibration bits (3 & 4) are set
        """
        status = self._read_status()
        return (status & AHT21_STATUS_CALIBRATED) == 0x18

    def _calculate_crc8(self, data: bytes) -> int:
        """
        Calculate CRC-8/MAXIM checksum.
        
        Algorithm: Polynomial 0x31, Init 0xFF
        Input: First 6 bytes of sensor response
        
        Args:
            data: Byte array (only first 6 bytes used)
        
        Returns:
            8-bit CRC checksum
        """
        crc = AHT21_CRC_INIT
        for byte in data[0:6]:  # Only status + raw data
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ AHT21_CRC_POLYNOMIAL
                else:
                    crc = crc << 1
            crc &= 0xFF  # Ensure 8-bit
        return crc
