import math
import requests
from PIL import Image
from io import BytesIO
from collections import Counter
import time
import csv  
import os  

# maximum numbers of image tiles to download
MAX_TILES = 25  # adjustable
TILE_SIZE = 256  # OSM image tile is 256x256

# Function to convert latitude and longitude to tile coordinates
def lat_lon_to_tile(lat, lon, zoom):
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x_tile = int((lon + 180.0) / 360.0 * n)
    y_tile = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)

    # make the reference ina reasonable range
    x_tile = max(0, min(x_tile, int(n) - 1))
    y_tile = max(0, min(y_tile, int(n) - 1))
    
    return x_tile, y_tile

# Function to convert tile coordinates + pixel position back to latitude/longitude
def tile_pixel_to_latlon(x_tile, y_tile, px, py, zoom):
    """  (px, py) to (lat, lon) """
    n = 2.0 ** zoom
    lon = x_tile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y_tile + py / TILE_SIZE) / n)))
    lat = math.degrees(lat_rad)
    return lat, lon + (px / TILE_SIZE) * (360.0 / n)

# Function to get all pixels' colors from a tile and return the tile URL
def get_tile_colors(x_tile, y_tile, zoom):
    tile_url = f"https://tile.openstreetmap.org/{zoom}/{x_tile}/{y_tile}.png"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    print(f"Fetching tile: {tile_url}")  # Print tile URL for debugging

    for attempt in range(3):  # Try up to 3 times
        try:
            response = requests.get(tile_url, headers=headers, timeout=10)
            response.raise_for_status()
            print(f"Successfully fetched tile {x_tile}, {y_tile}")
            break  # Exit loop if successful
        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch tile {x_tile}, {y_tile} (attempt {attempt+1}): {e}")
            time.sleep(2)  # Wait before retrying
    else:
        return tile_url, []  # Return URL with an empty list if failed

    tile_image = Image.open(BytesIO(response.content)).convert("RGB")
    pixels = list(tile_image.getdata())

    # convert the lat and lon to each pixel
    pixel_data = []
    for py in range(TILE_SIZE):
        for px in range(TILE_SIZE):
            lat, lon = tile_pixel_to_latlon(x_tile, y_tile, px, py, zoom)
            pixel_data.append((lat, lon, pixels[py * TILE_SIZE + px]))

    return tile_url, pixel_data  # return URL and (lat, lon, color) data

# Function to process the entire bounding box
def get_colors_from_bbox(min_lat, max_lat, min_lon, max_lon, zoom=16):
    # Convert lat/lon to tile indexes
    x_min, y_max = lat_lon_to_tile(min_lat, min_lon, zoom)  # Bottom-left tile
    x_max, y_min = lat_lon_to_tile(max_lat, max_lon, zoom)  # Top-right tile

    print(f"Tile range: x [{x_min}, {x_max}], y [{y_min}, {y_max}]")

    if x_min > x_max or y_min > y_max:
        print("Invalid tile range. Check latitude and longitude.")
        return [], 0, Counter(), []

    # caculate the number of image tiles to download
    tile_count = (x_max - x_min + 1) * (y_max - y_min + 1)
    if tile_count > MAX_TILES:
        print(f"exceeds the allowable image tile numbers ({MAX_TILES})")
        return [], 0, Counter(), []

    all_pixels = []
    pixel_coords = []  # save (lat, lon, color)
    tile_urls = []  # Store all fetched tile URLs

    for x_tile in range(x_min, x_max + 1):
        for y_tile in range(y_min, y_max + 1):  # make sure y_min < y_max
            tile_url, pixels = get_tile_colors(x_tile, y_tile, zoom)
            tile_urls.append(tile_url)  # Store the URL
            if pixels:
                all_pixels.extend([p[2] for p in pixels])  # extract color data
                pixel_coords.extend(pixels)  # save complete (lat, lon, color) data

    if not all_pixels:
        print("No pixels were fetched. Check the tile URLs and bounding box.")
        return [], 0, Counter(), tile_urls

    color_counts = Counter(all_pixels)
    return pixel_coords, len(color_counts), color_counts, tile_urls

# Function to save pixel data to CSV and surface material (combine RGB column)
def save_pixels_to_csv(pixel_data):
    """ Save labeled pixel data to CSV file on desktop (skip 'Unlabeled') """

    import os
    import csv

    # Define label categories with base RGB values
    color_labels = {
        "Asphalt": [(248, 250, 191), (232, 146, 161), (249, 178, 156), (255, 255, 255)],
        "Hardscape": [(255, 255, 228)],
        "Building": [(217, 208, 201)],
        "Parking Lot": [(237, 237, 237)],
        "Greenery": [(135, 224, 190), (205, 235, 176), (222, 252, 226), (173, 209, 158)],
    }

    def rgb_in_range(rgb, base_rgb, tolerance=5):
        """Check if the RGB color is within ±tolerance of base RGB"""
        return all(abs(rgb[i] - base_rgb[i]) <= tolerance for i in range(3))

    def get_label(rgb):
        """Assign a label to an RGB value based on defined categories with tolerance"""
        for label, base_colors in color_labels.items():
            for base in base_colors:
                if rgb_in_range(rgb, base):
                    return label
        return None  # Return None instead of "Unlabeled" to skip it

    # Save to desktop
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", "output.csv")
    with open(desktop_path, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Latitude", "Longitude", "RGB", "Label"])

        labeled_count = 0
        for lat, lon, color in pixel_data:
            label = get_label(color)
            if label:  # Skip if label is None (i.e., Unlabeled)
                rgb_str = f"({color[0]}, {color[1]}, {color[2]})"
                writer.writerow([lat, lon, rgb_str, label])
                labeled_count += 1

    print(f"\n📂 Data with {labeled_count} labeled rows saved to {desktop_path}")

# 🎯 Main function for user input
def main():
    # Define bounding box (min_lat, max_lat, min_lon, max_lon)
    min_lat = float(input("Enter minimum latitude: "))
    max_lat = float(input("Enter maximum latitude: "))
    min_lon = float(input("Enter minimum longitude: "))
    max_lon = float(input("Enter maximum longitude: "))

    # Process the bounding box
    pixel_data, unique_colors, color_counts, tile_urls = get_colors_from_bbox(min_lat, max_lat, min_lon, max_lon)

    if pixel_data:
        print(f"\n✅ Total pixels analyzed: {len(pixel_data)}")
        print(f"✅ Total unique colors: {unique_colors}")

        # Save to CSV
        save_pixels_to_csv(pixel_data)

    else:
        print("\n⚠️ No image tiles were retrieved. Please check your coordinates.")

# Run the main function
if __name__ == "__main__":
    main()
