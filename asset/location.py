import gps
from geopy.geocoders import Nominatim
from typing import Optional, Tuple, Dict
import time


class GPSLocator:
	def __init__(self, geocoder_user_agent: str = "myGeocoder"):
		"""
		Initialize GPS locator with optional geocoder settings.

		Args:
			geocoder_user_agent: User agent for Nominatim geocoder
		"""
		self.geolocator = Nominatim(user_agent=geocoder_user_agent)
		self.session = None

	def __enter__(self):
		"""Context manager entry (auto-connects to GPSD)"""
		self.connect()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		"""Context manager exit (auto-disconnects)"""
		self.disconnect()

	def connect(self):
		"""Connect to GPSD service"""
		self.session = gps.gps(mode=gps.WATCH_ENABLE | gps.WATCH_NEWSTYLE)
		return self

	def disconnect(self):
		"""Disconnect from GPSD"""
		if self.session:
			self.session.close()
			self.session = None

	def get_coordinates(self, timeout: int = 30) -> Optional[Tuple[float, float]]:
		"""
		Get current GPS coordinates.

		Args:
			timeout: Maximum seconds to wait for GPS lock

		Returns:
			Tuple of (latitude, longitude) or None if timeout
		"""
		start_time = time.time()
		while time.time() - start_time < timeout:
			try:
				report = self.session.next()
				if report['class'] == 'TPV':
					lat = report.get('lat', None)
					lon = report.get('lon', None)
					if lat is not None and lon is not None:
						return lat, lon
			except (StopIteration, KeyError):
				time.sleep(0.5)
		return None

	def get_address(self, coordinates: Tuple[float, float]) -> Optional[Dict]:
		"""
		Convert coordinates to human-readable address.

		Args:
			coordinates: Tuple of (latitude, longitude)

		Returns:
			Dictionary with address components or None if failed
		"""
		try:
			location = self.geolocator.reverse(coordinates, exactly_one=True)
			if location:
				return {
					'full_address': location.address,
					'raw': location.raw
				}
		except Exception as e:
			print(f"Geocoding error: {e}")
		return None

	def get_current_location(self) -> Optional[Dict]:
		"""
		Get complete location data (coordinates + address).

		Returns:
			Dictionary with both coordinates and address or None if failed
		"""
		coords = self.get_coordinates()
		if coords:
			address = self.get_address(coords)
			return {
				'coordinates': coords,
				'address': address
			}
		return None


# Example usage
if __name__ == "__main__":
	with GPSLocator() as locator:
		location = locator.get_current_location()
		if location:
			print(f"Coordinates: {location['coordinates']}")
			print(f"Address: {location['address']['full_address']}")
		else:
			print("Failed to get location")