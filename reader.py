import zxingcpp
import cv2
import sys
from datetime import datetime, timedelta
import pprint
import os
import glob
import json
import re
from PIL import Image
import tempfile

def parse_boarding_pass(data_string: str) -> list[dict]:
    """
    Parses an IATA Bar Coded Boarding Pass (BCBP) string, including multi-leg passes.
    Extracts both scheduled departure date and time when available.

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
            
            # Extract departure time from details block if available (positions 9-12 for HHMM format)
            departure_time_str = details_block[9:13] if len(details_block) >= 13 else "0000"
            try:
                hours = int(departure_time_str[:2])
                minutes = int(departure_time_str[2:4])
                departure_datetime = departure_date.replace(hour=hours, minute=minutes)
                flight_data['scheduled_departure_time'] = departure_datetime.isoformat()
            except (ValueError, IndexError):
                flight_data['scheduled_departure_time'] = departure_date.isoformat()
            
            # Extract arrival time if available (typically in conditional section or extended data)
            # For now, set as None - will be populated from conditional data if available
            flight_data['scheduled_arrival_time'] = None
            flight_data['actual_departure_time'] = None
            flight_data['actual_arrival_time'] = None
            
            # Keep departure_date for backward compatibility
            flight_data['scheduled_departure_date'] = departure_date.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            flight_data['scheduled_departure_date'] = None
            flight_data['scheduled_departure_time'] = None
            flight_data['scheduled_arrival_time'] = None
            flight_data['actual_departure_time'] = None
            flight_data['actual_arrival_time'] = None
            
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

def convert_to_png(image_path: str) -> str | None:
    """Converts an image to PNG format and returns the path to the converted file."""
    try:
        # Check if already PNG
        if image_path.lower().endswith('.png'):
            return image_path
        
        # Open image with PIL to handle various formats
        with Image.open(image_path) as img:
            # Convert to RGB if necessary (for formats like RGBA or P)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Create white background for transparent images
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Create temporary PNG file
            temp_dir = tempfile.gettempdir()
            base_name = os.path.splitext(os.path.basename(image_path))[0]
            temp_png_path = os.path.join(temp_dir, f"{base_name}_converted.png")
            
            # Save as PNG
            img.save(temp_png_path, 'PNG')
            return temp_png_path
            
    except Exception as e:
        print(f"    [!] Error converting {os.path.basename(image_path)} to PNG: {e}")
        return None

def process_image(image_path: str) -> list[dict] | None:
    """Decodes and parses a boarding pass from a single image file."""
    print(f"--> Processing {os.path.basename(image_path)}...")
    
    # Convert to PNG if necessary
    png_path = convert_to_png(image_path)
    if png_path is None:
        return None
    
    # Track if we created a temporary file
    is_temp_file = png_path != image_path
    
    try:
        img = cv2.imread(png_path)
        if img is None:
            print(f"    [!] Error: Could not open image at {png_path}")
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
    finally:
        # Clean up temporary file if we created one
        if is_temp_file and os.path.exists(png_path):
            try:
                os.remove(png_path)
            except:
                pass  # Ignore cleanup errors

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

    # Support multiple image formats
    supported_extensions = ['*.png', '*.jpg', '*.jpeg', '*.bmp', '*.tiff', '*.tif', '*.webp', '*.gif']
    image_files = []
    
    for ext in supported_extensions:
        image_files.extend(glob.glob(os.path.join(passes_directory, ext)))
        image_files.extend(glob.glob(os.path.join(passes_directory, ext.upper())))
    
    if not image_files:
        print(f"No supported image files found in the '{passes_directory}' directory.")
        print(f"Supported formats: {', '.join([ext.replace('*', '') for ext in supported_extensions])}")
        return

    all_passes_data = []
    for image_path in image_files:
        pass_data = process_image(image_path)
        if pass_data:
            all_passes_data.extend(pass_data)
        print("-" * 20)

    # Merge with existing data to preserve manually added flights and skiplag status
    existing_data = []
    if os.path.exists(output_json_file):
        with open(output_json_file, 'r') as f:
            existing_data = json.load(f)
    
    # Create a set of source files that are being processed
    processed_files = {os.path.basename(img_path) for img_path in image_files}
    
    print(f"Found {len(image_files)} image files to process:")
    for img_file in image_files:
        print(f"  - {os.path.basename(img_file)}")
    print()
    
    # Keep existing flights that are NOT from files being re-processed
    preserved_flights = [
        flight for flight in existing_data 
        if flight.get('source_file') not in processed_files
    ]
    
    # Create lookup for existing flights to preserve skiplag status and other manual changes
    existing_lookup = {}
    for flight in existing_data:
        # Use multiple keys for robust matching
        departure_date = flight.get('scheduled_departure_date') or (
            flight.get('scheduled_departure_time', '').split('T')[0] if flight.get('scheduled_departure_time') else None
        )
        key = f"{flight.get('confirmation_number')}-{flight.get('flight_number')}-{departure_date}"
        existing_lookup[key] = flight
    
    # Apply existing data to newly parsed flights
    for new_flight in all_passes_data:
        departure_date = new_flight.get('scheduled_departure_date')
        key = f"{new_flight.get('confirmation_number')}-{new_flight.get('flight_number')}-{departure_date}"
        
        if key in existing_lookup:
            existing_flight = existing_lookup[key]
            # Preserve manual fields
            new_flight['is_skiplagged'] = existing_flight.get('is_skiplagged', False)
            if existing_flight.get('flightera_link'):
                new_flight['flightera_link'] = existing_flight['flightera_link']
            if existing_flight.get('actual_departure_time'):
                new_flight['actual_departure_time'] = existing_flight['actual_departure_time']
            if existing_flight.get('scheduled_arrival_time'):
                new_flight['scheduled_arrival_time'] = existing_flight['scheduled_arrival_time']
            if existing_flight.get('actual_arrival_time'):
                new_flight['actual_arrival_time'] = existing_flight['actual_arrival_time']
    
    # Combine preserved flights with newly parsed flights
    final_data = preserved_flights + all_passes_data


    with open(output_json_file, 'w') as f:
        json.dump(final_data, f, indent=4, sort_keys=True)
        
    print(f"\n✅ Done! Processed {len(image_files)} image files.")
    print(f"Found {len(all_passes_data)} new flight legs from images.")
    print(f"Preserved {len(preserved_flights)} existing flights.")
    print(f"Total flights in database: {len(final_data)}.")
    print(f"Combined data saved to '{output_json_file}'")

if __name__ == "__main__":
    main()

