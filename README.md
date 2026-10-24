# Geosampling Application Tool
Standalone tool developed in Python for geosampling and labeling polygons of LULC based on drone images with an interactive interface and stores the results using GeoJSON files.

## 🔒 Security & Installation Guide

This application is open-source and developed for academic/research purposes by the **LabDrones** laboratory. Because it is a non-commercial research project, the binaries are **not digitally signed** by a commercial Certificate Authority. 

Currently, pre-compiled binaries are provided for **Windows** and **Linux** platforms only.

### 🪟 Windows (SmartScreen Bypass)
Since the installer (`.exe`) is not signed, Windows Defender SmartScreen will display a warning. You can safely bypass it by following these steps:
1. Double-click the installer executable.
2. A blue window stating *"Windows protected your PC"* will appear.
3. Click on **"More info"** (under the main text).
4. Click the **"Run anyway"** button that appears at the bottom.

### 🐧 Linux
Depending on your distribution, you may need to explicitly grant execution permissions to the binary before running it:
```bash
# Navigate to the download directory and make the binary executable
chmod +x geosampler-linux

# Run the application
./geosampler-linux
```

---

## 🛠️ Running from Source (Advanced)

If you prefer to run or audit the application directly from the source code, follow these steps to set up your environment:

### Prerequisites
* **Python 3.14** (or compatible version)
* Tkinter system package (required by PySimpleGUI on some Linux distributions, e.g., `sudo apt install python3-tk`)

### Environment Setup & Installation
```bash
# 1. Create a virtual environment
python -m venv venv

# 2. Activate the virtual environment
# On Linux/macOS:
source venv/bin/activate
# On Windows (Command Prompt):
# venv\Scripts\activate.bat

# 3. Upgrade package management tools
pip install --upgrade pip setuptools wheel

# 4. Install required dependencies
pip install matplotlib geopandas affine geopy folium pysimplegui defusedxml
```

### Running the App
```bash
python geosampler_app.py
```

---

## 📜 License

This project is licensed under the GPL-3.0 License.

## Acknowledgments

This work was supported by the Wellcome Trust through grant number 224694/Z/21/Z. 

This work was also supported by the São Paulo Research Foundation (FAPESP) through a Postdoctoral Fellowship grant number 2026/17040-5.
