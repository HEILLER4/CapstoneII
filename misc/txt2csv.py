import csv

with open("PH.txt", "r", encoding="utf-8") as infile, \
     open("../offline_locations.csv", "w", encoding="utf-8", newline="") as outfile:

    writer = csv.writer(outfile)
    writer.writerow(["name", "latitude", "longitude"])  # header

    for line in infile:
        parts = line.strip().split("\t")
        if len(parts) >= 6:
            name = parts[1]
            lat = parts[4]
            lon = parts[5]
            writer.writerow([name, lat, lon])
