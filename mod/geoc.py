# mod/opencage_geocoder.py

import requests

API_KEY = "a35ee41da1454752bbb1e83955cdcbad"  # Replace this with your real API key


def geocode_opencage(address):
    url = "https://api.opencagedata.com/geocode/v1/json"
    params = {
        "q": address,
        "key": API_KEY,
        "countrycode": "ph",
        "limit": 1,
        "language": "en"
    }

    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        if data["results"]:
            geometry = data["results"][0]["geometry"]
            return (geometry["lat"], geometry["lng"])
    except Exception as e:
        print(f"[ERROR] OpenCage geocoding failed: {e}")

    return None
