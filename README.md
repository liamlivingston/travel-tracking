# Travel Tracking

A simple tool to parse, display, and manage travel / boarding pass data.

---

## Table of Contents

- [Features](#features)  
- [Getting Started](#getting-started)  
  - [Prerequisites](#prerequisites)  
  - [Installation](#installation)  
  - [Running Locally](#running-locally)  
- [Usage](#usage)  
- [Project Structure](#project-structure)  
- [Configuration](#configuration)  
- [Contributing](#contributing)  
- [License](#license)

---

## Features

- Parse and read boarding pass data (JSON).  
- Generate viewable formats / templates.  
- Ability to temporarily store or stage data.  
- Basic image/aztec code / svg support.  

---

## Getting Started

### Prerequisites

You will need:

- Python (3.x)  
- pip (or similar Python package installer)  

### Installation

Clone this repo:

```bash
git clone https://github.com/liamlivingston/travel-tracking.git
cd travel-tracking
```

Create and activate a virtual environment (recommended):

```bash
python3 -m venv env
source env/bin/activate   # On macOS/Linux
env\Scripts\activate    # On Windows
```

Install dependencies:

```bash
pip3 install -r requirements.txt
```

### Running Locally

After installing:

```bash
python3 app.py
```

Make sure any required data files (e.g. `boarding_passes.json`) are present in the `data/` folder (or wherever your configuration points).

---

## Usage

1. Add or update boarding passes in JSON format.  
2. Run the reader/parser script (likely `reader.py`) to extract / parse information.  
3. Use `app.py` (or other interface) to view the parsed boarding passes, possibly via a template in `templates/`.  
4. Temporary staging / processing may use the `temp/` folder.  

---

## Project Structure

Here’s a high‑level look:

```
travel-tracking/
│
├── app.py                # Main application entrypoint, managing high‑level logic
├── reader.py             # Parser logic for boarding passes / data extraction
├── boarding_passes.json  # Sample or real data for boarding passes
├── templates/            # HTML / SVG / other templating assets
├── data/                 # Data storage (past / current travel / passes)
├── temp/                 # Temporary working files
├── requirements.txt      # Python dependency list
├── .gitignore            # Files/folders to ignore under version control
├── assets (e.g. images)   # Aztec codes / SVGs / images used for display
└── other utility scripts   # e.g. temp.py etc.
```

---

## Configuration

- Where to put / read data: (e.g. `data/boarding_passes.json`)  
- Templates: stored under `templates/` — modify if you want custom display or styling.  
- Static assets like images / Aztec/SVG codes under assets or root.  

---

## Contributing

Contributions are welcome! Here are some ways you can help:

- Fix bugs or errors found in parsing logic.  
- Improve UI or templating (better display).  
- Add unit tests.  
- Add support for more formats of boarding passes.  
- Improve documentation.  

To contribute:

1. Fork the repo  
2. Create a branch (`git checkout -b feature-name`)  
3. Make your changes & commit  
4. Open a pull request  

---

## License

Specify your license here. If none yet, consider adding one (MIT, Apache, etc.) so others know how they may use your code.
