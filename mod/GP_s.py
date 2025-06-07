from asset.location import GPSLocator

def get_current_location_info():
    with GPSLocator() as gps:
        return gps.get_current_location()

if __name__ == "__main__":
    loc = get_current_location_info()
    if loc:
        print("Coordinates:", loc['coordinates'])
        print("Address:", loc['address']['full_address'])
    else:
        print("Failed to acquire GPS location.")
