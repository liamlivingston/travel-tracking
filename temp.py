import requests
import csv
import json
import os
import io

# URL to the raw CSV file on GitHub
CSV_URL = 'https://raw.githubusercontent.com/lxndrblz/Airports/main/airports.csv'

# Define the output path for our application's JSON file
OUTPUT_DIR = 'data'
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'airports.json')

def process_row(row, airports_list):
    """Processes a single row from the CSV reader and adds it to the list if valid."""
    iata_code = row.get('code')
    
    # CORRECTED: The 'type' column in this CSV uses 'AP' for airports.
    # We now check for this specific value to correctly identify airports.
    if iata_code and row.get('type') == 'AP':
        try:
            # Create a dictionary in the format our Flask app expects
            airports_list.append({
                "iata": iata_code,
                "name": row.get('name'),
                "lat": float(row.get('latitude')),
                "lon": float(row.get('longitude'))
            })
        except (ValueError, TypeError):
            # Handle cases where latitude/longitude might not be valid numbers
            print(f"[Data Warning] Skipping airport '{iata_code}' due to invalid coordinate data in a row.")

def fetch_and_process_airports():
    """
    Fetches airport data from a remote CSV, processes it, and saves it as a JSON file.
    """
    print(f"Downloading airport data from {CSV_URL}...")
    
    # --- 1. Download the data ---
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'
        }
        response = requests.get(CSV_URL, headers=headers)
        response.raise_for_status()

        if not response.content:
            print("[Error] The downloaded file is empty.")
            return

    except requests.exceptions.RequestException as e:
        print(f"[Network Error] Failed to download the file. Please check your internet connection.")
        print(f"Details: {e}")
        return

    print("Download complete. Processing data...")
    
    airports_list = []
    
    # --- 2. Process the CSV data ---
    try:
        decoded_content = response.content.decode('utf-8-sig')
        csv_file = io.StringIO(decoded_content)
        reader = csv.DictReader(csv_file)
        
        for row in reader:
            process_row(row, airports_list)

    except (csv.Error, UnicodeDecodeError) as e:
        print(f"[Parsing Error] Failed to read or process the CSV data. The file format might be incorrect.")
        print(f"Details: {e}")
        return

    # Ensure the 'data' directory exists
    if not os.path.exists(OUTPUT_DIR):
        print(f"Creating directory '{OUTPUT_DIR}'...")
        os.makedirs(OUTPUT_DIR)
        
    # --- 3. Write the JSON file ---
    print(f"Processing complete. Attempting to write {len(airports_list)} airports to '{OUTPUT_FILE}'...")
    try:
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(airports_list, f, indent=4)
    except IOError as e:
        print(f"[File Error] Failed to write data to '{OUTPUT_FILE}'. Please check file and directory permissions.")
        print(f"Details: {e}")
        return
        
    print(f"\n✅ Success! Processed {len(airports_list)} airports.")
    print(f"Data saved to '{OUTPUT_FILE}'")

if __name__ == '__main__':
    fetch_and_process_airports()

