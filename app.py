from flask import Flask, render_template, jsonify, request
import json
import os

app = Flask(__name__)

# --- Configuration ---
PASS_DATA_FILE = 'boarding_passes.json'
AIRPORT_DATA_FILE = 'data/airports.json'

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
        
        # Generate a stable, unique ID for each flight for API calls
        flight['id'] = f"{flight.get('confirmation_number')}-{flight.get('flight_number')}-{flight.get('departure_date')}"
        
        enriched_flights.append(flight)

    # Sort flights by departure date, most recent first
    enriched_flights.sort(key=lambda x: x.get('departure_date', '0000-00-00'), reverse=True)
        
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
        current_flight_id = f"{flight.get('confirmation_number')}-{flight.get('flight_number')}-{flight.get('departure_date')}"
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
    required_fields = ['passenger_name', 'confirmation_number', 'departure_date', 'carrier', 'flight_number', 'origin', 'destination', 'cabin']
    if not all(field in new_flight_data for field in required_fields):
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    
    # Load the current flight data
    flights = load_json_data(PASS_DATA_FILE)

    # Construct the new flight object to match the structure from the parser
    new_flight = {
        "passenger_name": new_flight_data.get('passenger_name').upper(),
        "confirmation_number": new_flight_data.get('confirmation_number').upper(),
        "departure_date": new_flight_data.get('departure_date'),
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
        "julian_date": "000" # Default value
    }

    # Add the new flight to the list
    flights.append(new_flight)

    # Save the modified data back to the file
    save_json_data(flights, PASS_DATA_FILE)
    
    return jsonify({"success": True, "message": "Flight added successfully"})

if __name__ == '__main__':
    app.run(debug=True)

