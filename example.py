"""
ENS160 + AHT21 Sensor Integration Test Script
Demonstrates air quality monitoring with temperature/humidity compensation
"""

from machine import I2C, Pin
import time
from aht21 import (
    AHT21, 
    AHT21Error, 
    AHT21CalibrationError, 
    AHT21CRCError, 
    AHT21TimeoutError
)
from ens160 import (
    ENS160,
    ENS160Error,
    ENS160InitError,
    ENS160CommunicationError,
    ENS160DataError
)

# === Hardware Setup ===
print("=" * 50)
print("ENS160 + AHT21 Air Quality Monitor")
print("=" * 50)
print("\nInitializing I2C...")
i2c = I2C(
    0,
    scl=Pin(5),  # GP5
    sda=Pin(4),  # GP4
    freq=400_000  # 400kHz fast mode
)

# Scan for devices
devices = i2c.scan()
print(f"I2C devices found: {[hex(addr) for addr in devices]}")

# === Sensor Initialization ===
aht = None
ens = None

# Initialize AHT21
try:
    print("\nInitializing AHT21 temperature/humidity sensor...")
    aht = AHT21(i2c, address=0x38)
    print("✓ AHT21 calibrated and ready")
except AHT21CalibrationError as e:
    print(f"✗ AHT21 calibration failed: {e}")
    print("  Check: 3.3V power, I2C wiring, pull-up resistors")
    exit(1)
except OSError as e:
    print(f"✗ AHT21 I2C communication error: {e}")
    print("  Check: SDA/SCL connections, sensor address 0x38")
    exit(1)

# Initialize ENS160
try:
    print("Initializing ENS160 air quality sensor...")
    ens = ENS160(i2c, address=0x53)
    print("✓ ENS160 initialized and ready")
    
    # Get firmware version
    try:
        fw_version = ens.get_firmware_version()
        print(f"  Firmware version: {fw_version}")
    except:
        print("  (Firmware version unavailable)")
        
except ENS160InitError as e:
    print(f"✗ ENS160 initialization failed: {e}")
    print("  Check: Module wiring, I2C address should be 0x53")
    exit(1)
except OSError as e:
    print(f"✗ ENS160 I2C communication error: {e}")
    exit(1)

# === Measurement Loop ===
print("\n" + "=" * 50)
print("Starting measurements (Ctrl+C to stop)")
print("NOTE: ENS160 requires:")
print("  - 3 minutes warm-up after power-on")
print("  - 24 hours initial calibration (first use only)")
print("=" * 50 + "\n")

measurement_count = 0
valid_count = 0
error_count = 0
warmup_shown = False

# Statistics tracking
min_aqi = 5
max_aqi = 1
total_tvoc = 0
total_eco2 = 0

try:
    while True:
        measurement_count += 1
        
        try:
            # === Step 1: Read temperature and humidity ===
            temp, hum = aht.read_temperature_humidity()
            
            # === Step 2: Apply compensation to ENS160 ===
            ens.set_compensation(temp, hum)
            
            # === Step 3: Update ENS160 data ===
            data_valid = ens.update()
            
            # === Step 4: Display results ===
            # Always show temperature/humidity
            print(f"[{measurement_count:04d}] T:{temp:5.1f}°C H:{hum:5.1f}%RH | ", end="")
            
            if data_valid:
                # Valid data available
                valid_count += 1
                warmup_shown = False
                
                # Get AQI rating string
                rating = ens.AQI_RATINGS.get(ens.aqi, "Unknown")
                
                # Display air quality data
                print(f"AQI:{ens.aqi}({rating:9s}) TVOC:{ens.tvoc:5d}ppb eCO2:{ens.eco2:5d}ppm")
                
                # Update statistics
                if ens.aqi < min_aqi:
                    min_aqi = ens.aqi
                if ens.aqi > max_aqi:
                    max_aqi = ens.aqi
                total_tvoc += ens.tvoc
                total_eco2 += ens.eco2
                
                # Warning for poor air quality
                if ens.aqi >= 4:
                    print("   ⚠ Poor air quality - ventilation recommended!")
                    
            elif ens.status == "Warm-up":
                # Sensor is warming up (3 minutes after power-on)
                if not warmup_shown:
                    print("⏳ Warming up (3 min after power-on)...")
                    warmup_shown = True
                else:
                    # Shorter message after first time
                    print("⏳ Warming up...")
                    
            elif ens.status == "Initial Startup":
                # First-time calibration (24 hours)
                print("🔧 Initial calibration (24h continuous power needed)")
                
            else:
                # Other status (Error or Unknown)
                print(f"Status: {ens.status}")
            
        except AHT21CRCError as e:
            error_count += 1
            print(f"[{measurement_count:04d}] ⚠ AHT21 CRC Error: {e}")
            
        except AHT21TimeoutError as e:
            error_count += 1
            print(f"[{measurement_count:04d}] ⚠ AHT21 Timeout: {e}")
            
        except ENS160CommunicationError as e:
            error_count += 1
            print(f"[{measurement_count:04d}] ⚠ ENS160 Communication Error: {e}")
            
        except OSError as e:
            error_count += 1
            print(f"[{measurement_count:04d}] ⚠ I2C Error: {e}")
        
        # Sample every 2 seconds (ENS160 max rate is 1 Hz)
        time.sleep(2)

except KeyboardInterrupt:
    # === Display statistics on exit ===
    print("\n" + "=" * 50)
    print("✓ Shutdown gracefully")
    print("\nStatistics:")
    print(f"  Total measurements: {measurement_count}")
    print(f"  Valid readings: {valid_count}")
    print(f"  Errors: {error_count}")
    
    if valid_count > 0:
        error_rate = (error_count / measurement_count) * 100
        print(f"  Error rate: {error_rate:.2f}%")
        print(f"\nAir Quality Summary:")
        print(f"  Best AQI: {min_aqi} ({ens.AQI_RATINGS.get(min_aqi, 'Unknown')})")
        print(f"  Worst AQI: {max_aqi} ({ens.AQI_RATINGS.get(max_aqi, 'Unknown')})")
        print(f"  Average TVOC: {total_tvoc // valid_count} ppb")
        print(f"  Average eCO2: {total_eco2 // valid_count} ppm")
    else:
        print("\nNo valid readings obtained.")
        print("Note: ENS160 needs 3 minutes warm-up after power-on.")
