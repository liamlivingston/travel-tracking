from flask import Flask, render_template, jsonify, request
import json
import os
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re
import pytz
from urllib.parse import urlparse
import time
import random

app = Flask(__name__)

# --- Configuration ---
PASS_DATA_FILE = 'boarding_passes.json'
AIRPORT_DATA_FILE = 'data/airports.json'

def extract_date_from_datetime(datetime_str):
    """Extracts date from datetime string in ISO format."""
    if not datetime_str:
        return None
    try:
        dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d')
    except (ValueError, AttributeError):
        return None

def load_json_data(file_path):
    """Loads data from a JSON file."""
    if not os.path.exists(file_path):
        return []
    with open(file_path, 'r') as f:
        return json.load(f)

def save_json_data(data, file_path):
    """Saves data to a JSON file."""
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4, sort_keys=True)

@app.route('/')
def dashboard():
    """Renders the main dashboard page."""
    # Load flight and airport data
    flights = load_json_data(PASS_DATA_FILE)
    airports = load_json_data(AIRPORT_DATA_FILE)
    
    # Create a lookup dictionary for airport coordinates
    airport_coords = {airport['iata']: (airport['lat'], airport['lon']) for airport in airports}
    
    # Enrich flight data with coordinates and a unique ID for the frontend
    enriched_flights = []
    for i, flight in enumerate(flights):
        origin_iata = flight.get('origin')
        dest_iata = flight.get('destination')
        
        # Add coordinates if available
        flight['origin_coords'] = airport_coords.get(origin_iata)
        flight['dest_coords'] = airport_coords.get(dest_iata)
        
        # Extract date from scheduled_departure_time or fall back to scheduled_departure_date
        departure_date = extract_date_from_datetime(flight.get('scheduled_departure_time')) or flight.get('scheduled_departure_date')
        flight['departure_date'] = departure_date
        
        # Generate a stable, unique ID for each flight for API calls
        flight['id'] = f"{flight.get('confirmation_number')}-{flight.get('flight_number')}-{departure_date or 'unknown'}"
        
        enriched_flights.append(flight)

    # Sort flights by departure date, most recent first
    enriched_flights.sort(key=lambda x: x.get('departure_date') or '0000-00-00', reverse=True)
        
    return render_template('index.html', flights=enriched_flights)

@app.route('/api/toggle_skiplag', methods=['POST'])
def toggle_skiplag():
    """API endpoint to toggle the skiplag status of a flight."""
    data = request.get_json()
    flight_id_to_toggle = data.get('id')

    if not flight_id_to_toggle:
        return jsonify({"success": False, "error": "Flight ID is missing"}), 400

    # Load the current flight data
    flights = load_json_data(PASS_DATA_FILE)
    
    flight_found = False
    for flight in flights:
        # Generate the same unique ID to find the matching flight
        departure_date = extract_date_from_datetime(flight.get('scheduled_departure_time')) or flight.get('scheduled_departure_date')
        current_flight_id = f"{flight.get('confirmation_number')}-{flight.get('flight_number')}-{departure_date or 'unknown'}"
        if current_flight_id == flight_id_to_toggle:
            # Toggle the 'is_skiplagged' status
            flight['is_skiplagged'] = not flight.get('is_skiplagged', False)
            flight_found = True
            break
            
    if not flight_found:
        return jsonify({"success": False, "error": "Flight not found"}), 404

    # Save the modified data back to the file
    save_json_data(flights, PASS_DATA_FILE)
    
    return jsonify({"success": True, "new_status": flight['is_skiplagged']})

@app.route('/api/add_flight', methods=['POST'])
def add_flight():
    """API endpoint to manually add a new flight."""
    new_flight_data = request.get_json()

    if not new_flight_data:
        return jsonify({"success": False, "error": "Invalid data"}), 400

    # Basic validation
    required_fields = ['passenger_name', 'confirmation_number', 'carrier', 'flight_number', 'origin', 'destination', 'cabin']
    if not all(field in new_flight_data for field in required_fields):
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    
    # Load the current flight data
    flights = load_json_data(PASS_DATA_FILE)

    # Construct the new flight object to match the structure from the parser
    new_flight = {
        "passenger_name": new_flight_data.get('passenger_name').upper(),
        "confirmation_number": new_flight_data.get('confirmation_number').upper(),
        "carrier": new_flight_data.get('carrier').upper(),
        "flight_number": new_flight_data.get('flight_number'),
        "origin": new_flight_data.get('origin').upper(),
        "destination": new_flight_data.get('destination').upper(),
        "seat_number": new_flight_data.get('seat_number', '').upper(),
        "cabin": new_flight_data.get('cabin'),
        "sequence_number": 999, # Default sequence number for manual entries
        "source_file": "Manual Entry",
        "is_skiplagged": False,
        "eticket_indicator": "E", # Default value
        "julian_date": "000", # Default value
        "flightera_link": new_flight_data.get('flightera_link'),
        "scheduled_departure_time": new_flight_data.get('scheduled_departure_time'),
        "actual_departure_time": new_flight_data.get('actual_departure_time'),
        "scheduled_arrival_time": new_flight_data.get('scheduled_arrival_time'),
        "actual_arrival_time": new_flight_data.get('actual_arrival_time')
    }

    # Add the new flight to the list
    flights.append(new_flight)

    # Save the modified data back to the file
    save_json_data(flights, PASS_DATA_FILE)
    
    return jsonify({"success": True, "message": "Flight added successfully"})

@app.route('/api/update_flight', methods=['POST'])
def update_flight():
    """API endpoint to update an existing flight."""
    update_data = request.get_json()
    flight_id = update_data.get('id')

    if not flight_id:
        return jsonify({"success": False, "error": "Flight ID is missing"}), 400

    # Load the current flight data
    flights = load_json_data(PASS_DATA_FILE)
    
    flight_index = -1
    for i, flight in enumerate(flights):
        # Generate the unique ID to find the match
        departure_date = extract_date_from_datetime(flight.get('scheduled_departure_time')) or flight.get('scheduled_departure_date')
        current_flight_id = f"{flight.get('confirmation_number')}-{flight.get('flight_number')}-{departure_date or 'unknown'}"
        
        if current_flight_id == flight_id:
            flight_index = i
            break
    
    if flight_index == -1:
         return jsonify({"success": False, "error": "Flight not found"}), 404

    # Update fields if provided
    flight = flights[flight_index]
    
    # Update allowed fields
    if 'carrier' in update_data: flight['carrier'] = update_data['carrier'].upper()
    if 'flight_number' in update_data: flight['flight_number'] = update_data['flight_number']
    if 'origin' in update_data: flight['origin'] = update_data['origin'].upper()
    if 'destination' in update_data: flight['destination'] = update_data['destination'].upper()
    if 'scheduled_departure_time' in update_data: flight['scheduled_departure_time'] = update_data['scheduled_departure_time']
    if 'actual_departure_time' in update_data: flight['actual_departure_time'] = update_data['actual_departure_time']
    if 'scheduled_arrival_time' in update_data: flight['scheduled_arrival_time'] = update_data['scheduled_arrival_time']
    if 'actual_arrival_time' in update_data: flight['actual_arrival_time'] = update_data['actual_arrival_time']
    if 'flightera_link' in update_data: flight['flightera_link'] = update_data['flightera_link']
    
    # Save back
    flights[flight_index] = flight
    save_json_data(flights, PASS_DATA_FILE)

    return jsonify({"success": True, "message": "Flight updated successfully"})

def get_browser_headers():
    """Generate realistic browser headers to avoid detection."""
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0'
    ]
    
    return {
        'User-Agent': random.choice(user_agents),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"'
    }

def scrape_flightera_data(url):
    """
    Scrape flight data from Flightera URL with advanced anti-blocking techniques
    """
    session = requests.Session()
    
    # Rotating user agents
    user_agents = [
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0'
    ]
    
    for attempt in range(3):  # 3 retry attempts
        try:
            # Select random user agent
            user_agent = random.choice(user_agents)
            
            # Comprehensive browser headers
            headers = {
                'User-Agent': user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'UTF-8',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
            }
            
            # Add Chrome-specific headers if using Chrome user agent
            if 'Chrome' in user_agent:
                headers.update({
                    'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"macOS"'
                })
            
            # Add random delay to avoid rate limiting
            if attempt > 0:
                delay = random.uniform(1, 3) * (2 ** attempt)  # Exponential backoff
                time.sleep(delay)
            
            response = session.get(url, headers=headers, timeout=30)
            
            if response.status_code == 403:
                print(f"Attempt {attempt + 1}: 403 Forbidden - trying different user agent")
                continue
                
            response.raise_for_status()
            
            # Parse the HTML content
            soup = BeautifulSoup(response.content, 'html.parser')
            
            with open("temp/log.html", "w", encoding='utf-8') as file:
                file.write(str(soup.prettify()))
            
            # Extract flight data with improved patterns
            flight_data = {}
            
            # Get page text for pattern matching
            page_text = soup.get_text()
            print(f"Debug: Page text sample: {page_text[:1000]}...")  # Debug output
            
            # Also check for specific sections that might contain flight info
            flight_info_sections = soup.find_all(['div', 'span', 'td', 'th'], string=re.compile(r'(departure|arrival|time|TLV|Tel Aviv)', re.IGNORECASE))
            for section in flight_info_sections[:5]:  # Limit to first 5 matches
                parent_text = section.parent.get_text() if section.parent else section.get_text()
                print(f"Debug: Found relevant section: {parent_text[:200]}")
            
            # Look for table data that might contain times
            tables = soup.find_all('table')
            for i, table in enumerate(tables[:3]):  # Check first 3 tables
                table_text = table.get_text()
                if any(keyword in table_text.lower() for keyword in ['departure', 'arrival', 'time', 'scheduled', 'actual']):
                    print(f"Debug: Table {i} with time info: {table_text[:300]}")
            
            # First, try to extract from URL structure
            # URL format: /flight_details/United+Airlines/UA954/KSFO/2023-07-21
            url_parts = url.split('/')
            if len(url_parts) >= 6:
                try:
                    airline_part = url_parts[-4].replace('+', ' ')  # "United Airlines"
                    flight_part = url_parts[-3]  # "UA954"
                    airport_part = url_parts[-2]  # "KSFO"
                    
                    # Extract carrier and flight number from flight_part
                    flight_match = re.match(r'([A-Z]{2,3})(\d{1,4})', flight_part)
                    if flight_match:
                        flight_data['carrier'] = flight_match.group(1)
                        flight_data['flight_number'] = flight_match.group(2)
                    
                    # Extract origin airport (remove K prefix if present for US airports)
                    origin_code = airport_part
                    if origin_code.startswith('K') and len(origin_code) == 4:
                        origin_code = origin_code[1:]  # Remove K prefix (KSFO -> SFO)
                    flight_data['origin'] = origin_code
                    
                    print(f"Debug: Extracted from URL - Carrier: {flight_data.get('carrier')}, Flight: {flight_data.get('flight_number')}, Origin: {flight_data.get('origin')}")
                except Exception as e:
                    print(f"Debug: URL parsing failed: {e}")
            
            # Extract destination from page content with improved patterns
            # Look for route patterns like "SFO → TLV" or "SFO - TLV"
            route_patterns = [
                r'([A-Z]{3})\s*[→\->\u2192]\s*([A-Z]{3})',  # SFO → TLV
                r'From\s+([A-Z]{3})\s+to\s+([A-Z]{3})',  # From SFO to TLV
                r'([A-Z]{3})\s+to\s+([A-Z]{3})',  # SFO to TLV
                r'Route:\s*([A-Z]{3})\s*[→\->\u2192]\s*([A-Z]{3})',  # Route: SFO → TLV
                r'Departure:\s*([A-Z]{3}).*?Arrival:\s*([A-Z]{3})',  # Departure: SFO ... Arrival: TLV
                r'Origin:\s*([A-Z]{3}).*?Destination:\s*([A-Z]{3})',  # Origin: SFO ... Destination: TLV
            ]
            
            for pattern in route_patterns:
                match = re.search(pattern, page_text, re.DOTALL)
                if match:
                    potential_origin = match.group(1)
                    potential_dest = match.group(2)
                    
                    # If we already have origin from URL, use it, otherwise use from pattern
                    if 'origin' not in flight_data:
                        flight_data['origin'] = potential_origin
                    flight_data['destination'] = potential_dest
                    print(f"Debug: Route pattern matched - {potential_origin} → {potential_dest}")
                    break
            
            # If still no destination, try to find airport codes in sequence with better filtering
            if 'destination' not in flight_data:
                # Find all 3-letter airport codes, excluding common false positives
                airport_codes = re.findall(r'\b([A-Z]{3})\b', page_text)
                # Enhanced exclusion list
                excluded = {
                    'UTC', 'GMT', 'PST', 'EST', 'CST', 'MST', 'PDT', 'EDT', 'CDT', 'MDT', 
                    'API', 'URL', 'GPS', 'FAQ', 'CEO', 'CTO', 'CFO', 'THE', 'AND', 'FOR', 
                    'YOU', 'ARE', 'NOT', 'BUT', 'CAN', 'ALL', 'ANY', 'NEW', 'NOW', 'OLD', 
                    'SEE', 'TWO', 'WAY', 'WHO', 'BOY', 'DID', 'ITS', 'LET', 'OWN', 'SAY', 
                    'SHE', 'TOO', 'USE', 'VRD', 'GOY', 'APP', 'WEB', 'NET', 'COM', 'ORG', 'GOV',
                    'EDU', 'MIL', 'INT', 'BIZ', 'PRO', 'TEL', 'XXX', 'JOB', 'CAT', 'TOP'
                }
                valid_codes = [code for code in airport_codes if code not in excluded]
                
                print(f"Debug: Found airport codes: {valid_codes}")
                
                # Look specifically for common airport patterns after origin
                if 'origin' in flight_data:
                    origin = flight_data['origin']
                    origin_index = -1
                    
                    # Find where origin appears in the valid codes list
                    for i, code in enumerate(valid_codes):
                        if code == origin:
                            origin_index = i
                            break
                    
                    # If origin found, look for destination after it
                    if origin_index >= 0 and origin_index + 1 < len(valid_codes):
                        flight_data['destination'] = valid_codes[origin_index + 1]
                        print(f"Debug: Found destination after origin: {valid_codes[origin_index + 1]}")
                    elif len(valid_codes) >= 2:
                        # Find the first different airport code
                        for code in valid_codes:
                            if code != origin:
                                flight_data['destination'] = code
                                print(f"Debug: Found destination different from origin: {code}")
                                break
                elif len(valid_codes) >= 2:
                    flight_data['origin'] = valid_codes[0]
                    flight_data['destination'] = valid_codes[1]
            
            # Fallback: Extract flight number and carrier from page content if not from URL
            if 'carrier' not in flight_data or 'flight_number' not in flight_data:
                flight_patterns = [
                    r'Flight\s+([A-Z]{2,3})\s*(\d{1,4})',  # Flight UA 954
                    r'([A-Z]{2,3})\s*(\d{1,4})',  # UA 954
                    r'([A-Z]{2,3})(\d{1,4})',  # UA954
                ]
                
                for pattern in flight_patterns:
                    match = re.search(pattern, page_text)
                    if match:
                        flight_data['carrier'] = match.group(1)
                        flight_data['flight_number'] = match.group(2)
                        print(f"Debug: Flight pattern matched - {match.group(1)}{match.group(2)}")
                        break
            
            # Extract departure and arrival dates separately
            departure_date = None
            arrival_date = None
            
            # Convert month abbreviation to number helper
            months = {'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
                     'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'}
            
            # Look for departure date in the main header (e.g., "21. Jul 2023")
            date_elem = soup.find('div', {'itemprop': 'departureTime'})
            if date_elem:
                date_text = date_elem.get_text(strip=True)
                date_match = re.search(r'(\d{1,2})\.\s*(\w{3})\s*(\d{4})', date_text)
                if date_match:
                    day, month, year = date_match.groups()
                    if month in months:
                        departure_date = f"{year}-{months[month]}-{day.zfill(2)}"
                        print(f"Debug: Found departure date: {departure_date}")
            
            # Look for arrival date in structured data (JSON-LD)
            json_ld_scripts = soup.find_all('script', type='application/ld+json')
            for script in json_ld_scripts:
                try:
                    import json
                    data = json.loads(script.string)
                    if isinstance(data, dict) and data.get('@type') == 'Flight':
                        arrival_time = data.get('arrivalTime')
                        if arrival_time:
                            # Parse ISO datetime (e.g., "2023-07-22T17:00:00Z")
                            arrival_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', arrival_time)
                            if arrival_match:
                                year, month, day = arrival_match.groups()
                                arrival_date = f"{year}-{month}-{day}"
                                print(f"Debug: Found arrival date from JSON-LD: {arrival_date}")
                                break
                except (json.JSONDecodeError, AttributeError):
                    continue
            
            # Fallback: try to extract dates from meta description
            if not departure_date or not arrival_date:
                meta_desc = soup.find('meta', {'name': 'description'})
                if meta_desc:
                    desc_text = meta_desc.get('content', '')
                    # Look for pattern like "22. Jul 2023:" which might be arrival date
                    date_matches = re.findall(r'(\d{1,2})\.\s*(\w{3})\s*(\d{4})', desc_text)
                    if len(date_matches) >= 2:
                        # First date is usually departure, second is arrival
                        if not departure_date:
                            day, month, year = date_matches[0]
                            if month in months:
                                departure_date = f"{year}-{months[month]}-{day.zfill(2)}"
                                print(f"Debug: Found departure date from meta: {departure_date}")
                        if not arrival_date:
                            day, month, year = date_matches[1] if len(date_matches) > 1 else date_matches[0]
                            if month in months:
                                arrival_date = f"{year}-{months[month]}-{day.zfill(2)}"
                                print(f"Debug: Found arrival date from meta: {arrival_date}")
            
            # If no separate arrival date found, use departure date
            if not arrival_date and departure_date:
                arrival_date = departure_date
                print(f"Debug: Using departure date for arrival: {arrival_date}")
            
            # Extract comprehensive time information using HTML structure
            print(f"Debug: Searching for time patterns in HTML structure...")
            
            # Extract departure and arrival airports from meta tags
            dep_airport_meta = soup.find('meta', {'itemprop': 'departureAirport'})
            if dep_airport_meta:
                flight_data['origin'] = dep_airport_meta.get('content', '')
                print(f"Debug: Found origin airport from meta: {flight_data['origin']}")
            
            arr_airport_meta = soup.find('meta', {'itemprop': 'arrivalAirport'})
            if arr_airport_meta:
                flight_data['destination'] = arr_airport_meta.get('content', '')
                print(f"Debug: Found destination airport from meta: {flight_data['destination']}")
            
            # Fallback: Extract from airport links if meta tags not found
            if not flight_data.get('origin'):
                dep_airport_elem = soup.find('div', string='DEPARTURE')
                if dep_airport_elem:
                    dep_container = dep_airport_elem.find_parent()
                    if dep_container:
                        # Look for airport code in nearby elements
                        airport_links = dep_container.find_all('a')
                        for link in airport_links:
                            if '/airport/' in link.get('href', ''):
                                flight_data['origin'] = link.get_text(strip=True)
                                print(f"Debug: Found origin airport from fallback: {flight_data['origin']}")
                                break
            
            if not flight_data.get('destination'):
                arr_airport_elem = soup.find('div', string='ARRIVAL')
                if arr_airport_elem:
                    arr_container = arr_airport_elem.find_parent()
                    if arr_container:
                        # Look for airport code in nearby elements
                        airport_links = arr_container.find_all('a')
                        for link in airport_links:
                            if '/airport/' in link.get('href', ''):
                                flight_data['destination'] = link.get_text(strip=True)
                                print(f"Debug: Found destination airport from fallback: {flight_data['destination']}")
                                break

            # Look for actual departure time (in main time display)
            dep_time_elem = soup.find('div', {'id': 'depTimeLiveHB'})
            if dep_time_elem:
                time_text = dep_time_elem.get_text(strip=True)
                time_match = re.search(r'(\d{1,2}:\d{2})', time_text)
                if time_match:
                    time_str = time_match.group(1)
                    if departure_date:
                        flight_data['actual_departure_time'] = f"{departure_date}T{time_str}"
                    else:
                        flight_data['actual_departure_time'] = time_str
                    print(f"Debug: Found actual departure time: {flight_data['actual_departure_time']}")
                
                # Extract departure timezone
                timezone_span = dep_time_elem.find('span', class_='text-xs')
                if timezone_span:
                    timezone = timezone_span.get_text(strip=True)
                    flight_data['departure_timezone'] = timezone
                    print(f"Debug: Found departure timezone: {timezone}")
            
            # Look for actual arrival time (in main time display)
            arr_time_elem = soup.find('div', {'id': 'arrTimeLiveHB'})
            if arr_time_elem:
                time_text = arr_time_elem.get_text(strip=True)
                time_match = re.search(r'(\d{1,2}:\d{2})', time_text)
                if time_match:
                    time_str = time_match.group(1)
                    if arrival_date:
                        flight_data['actual_arrival_time'] = f"{arrival_date}T{time_str}"
                    else:
                        flight_data['actual_arrival_time'] = time_str
                    print(f"Debug: Found actual arrival time: {flight_data['actual_arrival_time']}")
                
                # Extract arrival timezone
                timezone_span = arr_time_elem.find('span', class_='text-xs')
                if timezone_span:
                    timezone = timezone_span.get_text(strip=True)
                    flight_data['arrival_timezone'] = timezone
                    print(f"Debug: Found arrival timezone: {timezone}")
            
            # Look for scheduled departure time (in strikethrough)
            dep_section = soup.find('div', string='DEPARTURE')
            if dep_section:
                dep_container = dep_section.find_parent()
                if dep_container:
                    strikethrough = dep_container.find('span', class_='line-through')
                    if strikethrough:
                        scheduled_time = strikethrough.get_text(strip=True)
                        if departure_date:
                            flight_data['scheduled_departure_time'] = f"{departure_date}T{scheduled_time}"
                        else:
                            flight_data['scheduled_departure_time'] = scheduled_time
                        print(f"Debug: Found scheduled departure time: {flight_data['scheduled_departure_time']}")
            
            # Look for scheduled arrival time (in strikethrough)
            arr_section = soup.find('div', string='ARRIVAL')
            if arr_section:
                arr_container = arr_section.find_parent()
                if arr_container:
                    strikethrough = arr_container.find('span', class_='line-through')
                    if strikethrough:
                        scheduled_time = strikethrough.get_text(strip=True)
                        if arrival_date:
                            flight_data['scheduled_arrival_time'] = f"{arrival_date}T{scheduled_time}"
                        else:
                            flight_data['scheduled_arrival_time'] = scheduled_time
                        print(f"Debug: Found scheduled arrival time: {flight_data['scheduled_arrival_time']}")
            
            # Extract delay information
            dep_delay_elem = soup.find('span', {'id': 'depDelHB'})
            if dep_delay_elem:
                delay_minutes = dep_delay_elem.get_text(strip=True)
                flight_data['departure_delay_minutes'] = delay_minutes
                print(f"Debug: Found departure delay: {delay_minutes} minutes")
            
            arr_delay_elem = soup.find('span', {'id': 'arrDelHB'})
            if arr_delay_elem:
                delay_minutes = arr_delay_elem.get_text(strip=True)
                flight_data['arrival_delay_minutes'] = delay_minutes
                print(f"Debug: Found arrival delay: {delay_minutes} minutes")
            
            # Handle cases with no delays - set actual times equal to scheduled times and ensure scheduled times are included
            if flight_data.get('scheduled_departure_time') and not flight_data.get('actual_departure_time'):
                flight_data['actual_departure_time'] = flight_data['scheduled_departure_time']
                print(f"Debug: No departure delay detected - setting actual departure time to scheduled: {flight_data['actual_departure_time']}")
            elif flight_data.get('actual_departure_time') and not flight_data.get('scheduled_departure_time') and flight_data.get('departure_delay_minutes') == '0':
                flight_data['scheduled_departure_time'] = flight_data['actual_departure_time']
                print(f"Debug: Zero delay detected - setting scheduled departure time to actual: {flight_data['scheduled_departure_time']}")
            
            if flight_data.get('scheduled_arrival_time') and not flight_data.get('actual_arrival_time'):
                flight_data['actual_arrival_time'] = flight_data['scheduled_arrival_time']
                print(f"Debug: No arrival delay detected - setting actual arrival time to scheduled: {flight_data['actual_arrival_time']}")
            elif flight_data.get('actual_arrival_time') and not flight_data.get('scheduled_arrival_time') and flight_data.get('arrival_delay_minutes') == '0':
                flight_data['scheduled_arrival_time'] = flight_data['actual_arrival_time']
                print(f"Debug: Zero delay detected - setting scheduled arrival time to actual: {flight_data['scheduled_arrival_time']}")
            
            # Fallback: Look for any time patterns in text if HTML parsing fails
            if not any(key in flight_data for key in ['scheduled_departure_time', 'actual_departure_time', 'scheduled_arrival_time', 'actual_arrival_time']):
                all_times = re.findall(r'(\d{1,2}:\d{2})\s*(AM|PM)?', page_text, re.IGNORECASE)
                print(f"Debug: Fallback - All times found on page: {all_times[:10]}")  # Show first 10 times
            
            
            print(f"Debug: Final extracted data: {flight_data}")
            return flight_data
            
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt == 2:  # Last attempt
                raise Exception(f"Failed to fetch data after 3 attempts: {str(e)}")
    
    return {}

@app.route('/api/scrape_flightera', methods=['POST'])
def scrape_flightera():
    """API endpoint to scrape flight data from Flightera URL."""
    data = request.get_json()
    flightera_url = data.get('url')
    
    if not flightera_url:
        return jsonify({"success": False, "error": "Flightera URL is required"}), 400
    
    try:
        # Validate URL
        parsed_url = urlparse(flightera_url)
        if 'flightera.net' not in parsed_url.netloc:
            return jsonify({"success": False, "error": "Invalid Flightera URL"}), 400
        
        flight_data = scrape_flightera_data(flightera_url)
        
        return jsonify({
            "success": True, 
            "data": flight_data,
            "message": "Flight data scraped successfully"
        })
        
    except requests.RequestException as e:
        return jsonify({"success": False, "error": f"Network error: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"Parsing error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)

