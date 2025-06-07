import serial
import time
from geopy.geocoders import Nominatim
from typing import Optional, Tuple, Dict

class GPSLocator:
    def __init__(self, port: str = "/dev/serial0", baudrate: int = 115200, timeout: int = 1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn = None
        self.geolocator = Nominatim(user_agent="gps_locator")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def connect(self):
        self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=self.timeout)

    def disconnect(self):
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()

    def parse_GPRMC(self, sentence: str) -> Optional[Tuple[float, float]]:
        try:
            parts = sentence.split(',')
            if parts[0].startswith('$GPRMC') and parts[2] == 'A':  # A = Active (valid)
                lat = self.nmea_to_decimal(parts[3], parts[4])
                lon = self.nmea_to_decimal(parts[5], parts[6])
                return lat, lon
        except Exception:
            pass
        return None

    def nmea_to_decimal(self, raw_value: str, direction: str) -> float:
        if not raw_value:
            return 0.0
        degrees = float(raw_value[:2])
        minutes = float(raw_value[2:])
        decimal = degrees + (minutes / 60)
        if direction in ['S', 'W']:
            decimal *= -1
        return decimal

    def get_coordinates(self, timeout: int = 20) -> Optional[Tuple[float, float]]:
        if not self.serial_conn:
            self.connect()

        start = time.time()
        while time.time() - start < timeout:
            try:
                line = self.serial_conn.readline().decode('ascii', errors='ignore').strip()
                coords = self.parse_GPRMC(line)
                if coords:
                    return coords
            except Exception:
                pass
        return None

    def get_address(self, coordinates: Tuple[float, float]) -> Optional[Dict]:
        try:
            location = self.geolocator.reverse(coordinates, exactly_one=True)
            if location:
                return {
                    'full_address': location.address,
                    'raw': location.raw
                }
        except Exception as e:
            print(f"[Geocode] Error: {e}")
        return None

    def get_current_location(self) -> Optional[Dict]:
        coords = self.get_coordinates()
        if coords:
            address = self.get_address(coords)
            return {
                'coordinates': coords,
                'address': address
            }
        return None


# For manual testing
if __name__ == "__main__":
    with GPSLocator() as gps:
        loc = gps.get_current_location()
        if loc:
            print(f"Coordinates: {loc['coordinates']}")
            print(f"Address: {loc['address']['full_address']}")
        else:
            print("Location could not be determined.")
