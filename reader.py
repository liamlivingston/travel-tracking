import zxingcpp
import cv2
import sys
from datetime import datetime, timedelta
import pprint
import os
import glob
import json
import re

def parse_boarding_pass(data_string: str) -> list[dict]:
    """
    Parses an IATA Bar Coded Boarding Pass (BCBP) string, including multi-leg passes.

    Args:
        data_string: The raw text data from the Aztec code.

    Returns:
        A list of dictionaries, where each dictionary represents one flight leg.
    """
    all_flights = []
    
    # --- 1. Parse Common Data (applies to all legs) ---
    common_data = {}
    try:
        common_data['format_code'] = data_string[0]
        legs_encoded = int(data_string[1])
        common_data['passenger_name'] = data_string[2:22].strip()
        pnr_field = data_string[22:29]
        common_data['eticket_indicator'] = pnr_field[0]
        common_data['confirmation_number'] = pnr_field[1:].strip()
    except (IndexError, ValueError) as e:
        raise ValueError(f"Failed to parse common header data: {e}")

    # --- 2. Find and Parse Each Flight Leg ---
    leg_pattern = re.compile(r"([A-Z]{8})\s+([0-9A-Z]{1,5})\s+([A-Z0-9]{12,13})")
    
    for match in leg_pattern.finditer(data_string):
        flight_data = common_data.copy()
        
        # Add the new skiplag field, default to false
        flight_data['is_skiplagged'] = False

        route_carrier_block, flight_number_str, details_block = match.groups()

        flight_data['origin'] = route_carrier_block[0:3]
        flight_data['destination'] = route_carrier_block[3:6]
        flight_data['carrier'] = route_carrier_block[6:].strip()
        flight_data['flight_number'] = flight_number_str.lstrip('0 ')
        julian_date_str = details_block[0:3]
        flight_data['julian_date'] = julian_date_str
        
        try:
            julian_date = int(julian_date_str)
            today = datetime.now()
            departure_date = datetime(today.year, 1, 1) + timedelta(days=julian_date - 1)
            if (departure_date - today).days > 180:
                 departure_date = datetime(today.year - 1, 1, 1) + timedelta(days=julian_date - 1)
            elif (today - departure_date).days > 180:
                departure_date = datetime(today.year + 1, 1, 1) + timedelta(days=julian_date - 1)
            flight_data['departure_date'] = departure_date.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            flight_data['departure_date'] = None
            
        cabin_code = details_block[3:4]
        cabin_map = {
            'F': 'First', 'A': 'First', 'J': 'Business', 'C': 'Business', 
            'D': 'Business', 'I': 'Business', 'W': 'Premium Economy', 
            'P': 'Premium Economy', 'Y': 'Economy', 'S': 'Economy', 
            'B': 'Economy', 'H': 'Economy', 'K': 'Economy', 'L': 'Economy', 
            'M': 'Economy', 'N': 'Economy'
        }
        flight_data['cabin'] = cabin_map.get(cabin_code, f"Unknown Code ({cabin_code})")
        
        seat_str = details_block[4:8]
        flight_data['seat_number'] = f"{int(seat_str[0:3])}{seat_str[3]}"
        
        sequence_str = details_block[8:12]
        flight_data['sequence_number'] = int(sequence_str)
        
        all_flights.append(flight_data)

    # --- 3. Parse Conditional Data (Ticket #, FF #) and add to the FIRST leg ---
    if ">" in data_string and all_flights:
        _, conditional_section = data_string.split('>', 1)
        conditional_parts = conditional_section.split()
        
        for part in conditional_parts:
            if part.startswith('2A') and part[2:].isdigit():
                all_flights[0]['ticket_number'] = part[2:-1] 
                break
        
        for i, part in enumerate(conditional_parts):
            if part == all_flights[0].get('carrier') and i + 2 < len(conditional_parts):
                if conditional_parts[i+2].isdigit() and len(conditional_parts[i+2]) > 5:
                    all_flights[0]['frequent_flyer_airline'] = part
                    all_flights[0]['frequent_flyer_number'] = conditional_parts[i+2]
                    break

    if not all_flights:
        raise ValueError("Could not find any valid flight leg data in the string.")

    return all_flights

def process_image(image_path: str) -> list[dict] | None:
    """Decodes and parses a boarding pass from a single image file."""
    print(f"--> Processing {os.path.basename(image_path)}...")
    img = cv2.imread(image_path)
    if img is None:
        print(f"    [!] Error: Could not open image at {image_path}")
        return None

    results = zxingcpp.read_barcodes(img)
    if not results:
        print(f"    [!] No Aztec code detected in {os.path.basename(image_path)}.")
        return None

    res = results[0]
    try:
        parsed_flights = parse_boarding_pass(res.text)
        for flight in parsed_flights:
            flight['source_file'] = os.path.basename(image_path)
        print(f"    [✓] Successfully parsed {len(parsed_flights)} flight leg(s).")
        return parsed_flights
    except Exception as e:
        print(f"    [!] An error occurred during parsing: {e}")
        return None

def main():
    """
    Main function to scan a directory for boarding pass images,
    parse them, and save the combined data to a JSON file.
    """
    passes_directory = 'passes'
    output_json_file = 'boarding_passes.json'
    
    if not os.path.isdir(passes_directory):
        print(f"Error: Directory '{passes_directory}' not found. Please create it and add your boarding pass PNGs.")
        return

    image_files = glob.glob(os.path.join(passes_directory, '*.png'))
    
    if not image_files:
        print(f"No .png files found in the '{passes_directory}' directory.")
        return

    all_passes_data = []
    for image_path in image_files:
        pass_data = process_image(image_path)
        if pass_data:
            all_passes_data.extend(pass_data)
        print("-" * 20)

    # Before saving, check existing data to preserve skiplag status if a file is re-processed.
    # This is a simple implementation. A more robust one might use a database.
    if os.path.exists(output_json_file):
        with open(output_json_file, 'r') as f:
            existing_data = json.load(f)
            # Create a lookup for existing skiplag statuses
            skiplag_lookup = {
                f"{d.get('confirmation_number')}-{d.get('flight_number')}-{d.get('departure_date')}": d.get('is_skiplagged', False)
                for d in existing_data
            }
            # Apply the old status to the new data
            for new_pass in all_passes_data:
                 key = f"{new_pass.get('confirmation_number')}-{new_pass.get('flight_number')}-{new_pass.get('departure_date')}"
                 if key in skiplag_lookup:
                     new_pass['is_skiplagged'] = skiplag_lookup[key]


    with open(output_json_file, 'w') as f:
        json.dump(all_passes_data, f, indent=4, sort_keys=True)
        
    print(f"\n✅ Done! Processed {len(image_files)} image files.")
    print(f"Found a total of {len(all_passes_data)} flight legs.")
    print(f"Combined data saved to '{output_json_file}'")

if __name__ == "__main__":
    main()

