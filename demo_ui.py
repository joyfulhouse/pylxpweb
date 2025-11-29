#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.12"
# dependencies = ["flask", "pylxpweb", "zoneinfo"]
# ///
"""
Solar Dashboard - 3D Visualization of Solar Array and Live Stats

A single-file Flask application with Three.js frontend showing:
- Animated sun position based on real astronomical calculations
- 3D roof with solar panels at correct azimuths (217° SW, 37° NE)
- Live inverter stats with real-time polling

Run with: uv run python solar_dashboard.py
Then open: http://localhost:5000
"""

import asyncio
import math
import sys
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Add the src directory to path for local development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from flask import Flask, jsonify, render_template_string

from pylxpweb import LuxpowerClient
from pylxpweb.devices.station import Station

# =============================================================================
# CONFIGURATION
# =============================================================================

# Oakland, California coordinates
LATITUDE = 37.8044
LONGITUDE = -122.2712
TIMEZONE = ZoneInfo("America/Los_Angeles")

# Solar array configuration
ARRAY_SIZE_KW = 14.0
PANEL_TILT = 20.0  # Roof pitch in degrees

# Roof faces
ROOF_FACES = [
    {"name": "SW Face", "azimuth": 217.0, "fraction": 0.5},
    {"name": "NE Face", "azimuth": 37.0, "fraction": 0.5},
]

# Inverter credentials
INVERTER_CONFIG = {
    "username": "<Your username here>",
    "password": "<Your password here>",
    "base_url": "https://monitor.eg4electronics.com"
}

# =============================================================================
# SOLAR CALCULATIONS (same as run.py)
# =============================================================================

def calculate_solar_position(dt: datetime, latitude: float, longitude: float) -> dict:
    """Calculate sun position for a given time and location."""
    dt_utc = dt.astimezone(timezone.utc)

    year = dt_utc.year
    month = dt_utc.month
    day = dt_utc.day
    hour = dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0

    if month <= 2:
        year -= 1
        month += 12

    A = int(year / 100)
    B = 2 - A + int(A / 4)
    JD = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + hour / 24.0 + B - 1524.5
    T = (JD - 2451545.0) / 36525.0

    L0 = (280.46646 + 36000.76983 * T + 0.0003032 * T**2) % 360
    M = (357.52911 + 35999.05029 * T - 0.0001537 * T**2) % 360
    M_rad = math.radians(M)
    e = 0.016708634 - 0.000042037 * T - 0.0000001267 * T**2

    C = ((1.914602 - 0.004817 * T - 0.000014 * T**2) * math.sin(M_rad) +
         (0.019993 - 0.000101 * T) * math.sin(2 * M_rad) +
         0.000289 * math.sin(3 * M_rad))

    sun_lon = L0 + C
    omega = 125.04 - 1934.136 * T
    sun_lon_apparent = sun_lon - 0.00569 - 0.00478 * math.sin(math.radians(omega))

    obliquity = 23.439291 - 0.013004 * T
    obliquity_corrected = obliquity + 0.00256 * math.cos(math.radians(omega))
    obliquity_rad = math.radians(obliquity_corrected)

    sun_lon_rad = math.radians(sun_lon_apparent)
    declination = math.degrees(math.asin(math.sin(obliquity_rad) * math.sin(sun_lon_rad)))

    y = math.tan(obliquity_rad / 2) ** 2
    L0_rad = math.radians(L0)
    eq_time = 4 * math.degrees(
        y * math.sin(2 * L0_rad) -
        2 * e * math.sin(M_rad) +
        4 * e * y * math.sin(M_rad) * math.cos(2 * L0_rad) -
        0.5 * y**2 * math.sin(4 * L0_rad) -
        1.25 * e**2 * math.sin(2 * M_rad)
    )

    solar_noon_utc = 720 - 4 * longitude - eq_time
    current_time_utc = hour * 60
    hour_angle = (current_time_utc - solar_noon_utc) / 4
    hour_angle_rad = math.radians(hour_angle)

    lat_rad = math.radians(latitude)
    dec_rad = math.radians(declination)

    sin_altitude = (math.sin(lat_rad) * math.sin(dec_rad) +
                    math.cos(lat_rad) * math.cos(dec_rad) * math.cos(hour_angle_rad))
    altitude = math.degrees(math.asin(max(-1, min(1, sin_altitude))))

    cos_azimuth = ((math.sin(dec_rad) - math.sin(lat_rad) * sin_altitude) /
                   (math.cos(lat_rad) * math.cos(math.radians(altitude)))) if altitude != 0 else 0
    cos_azimuth = max(-1, min(1, cos_azimuth))
    azimuth = math.degrees(math.acos(cos_azimuth))
    if hour_angle > 0:
        azimuth = 360 - azimuth

    # Sunrise/sunset
    cos_ha_sunrise = -math.tan(lat_rad) * math.tan(dec_rad)
    if cos_ha_sunrise >= 1:
        sunrise_hour, sunset_hour = None, None
    elif cos_ha_sunrise <= -1:
        sunrise_hour, sunset_hour = 0, 24
    else:
        ha_sunrise = math.degrees(math.acos(cos_ha_sunrise))
        sunrise_utc = solar_noon_utc - ha_sunrise * 4
        sunset_utc = solar_noon_utc + ha_sunrise * 4
        local_offset = dt.utcoffset().total_seconds() / 3600 if dt.utcoffset() else 0
        sunrise_hour = (sunrise_utc / 60 + local_offset) % 24
        sunset_hour = (sunset_utc / 60 + local_offset) % 24

    return {
        "altitude": altitude,
        "azimuth": azimuth,
        "sunrise_hour": sunrise_hour,
        "sunset_hour": sunset_hour,
        "is_daylight": altitude > 0,
    }


def calculate_clear_sky_dni(altitude: float) -> float:
    """Calculate clear-sky Direct Normal Irradiance."""
    if altitude <= 0:
        return 0.0
    altitude_rad = math.radians(altitude)
    air_mass = 1.0 / (math.sin(altitude_rad) + 0.50572 * (altitude + 6.07995) ** -1.6364)
    transmittance = 0.7 ** (air_mass ** 0.678)
    return 1361.0 * transmittance


def calculate_panel_irradiance(sun_alt: float, sun_az: float, panel_tilt: float, panel_az: float, dni: float) -> float:
    """Calculate irradiance on a tilted panel."""
    if sun_alt <= 0 or dni <= 0:
        return 0.0

    sun_alt_rad = math.radians(sun_alt)
    sun_az_rad = math.radians(sun_az)
    panel_tilt_rad = math.radians(panel_tilt)
    panel_az_rad = math.radians(panel_az)

    cos_incidence = (
        math.sin(sun_alt_rad) * math.cos(panel_tilt_rad) +
        math.cos(sun_alt_rad) * math.sin(panel_tilt_rad) * math.cos(sun_az_rad - panel_az_rad)
    )

    if cos_incidence <= 0:
        return 0.0

    direct = dni * cos_incidence
    ghi = dni * math.sin(sun_alt_rad)
    diffuse = ghi * 0.1 * (1 + math.cos(panel_tilt_rad)) / 2
    return direct + diffuse


# =============================================================================
# INVERTER DATA FETCHING
# =============================================================================

# Global cache for inverter data
_inverter_cache = {
    "data": None,
    "last_update": None
}


async def fetch_inverter_data():
    """Fetch live data from inverter."""
    try:
        async with LuxpowerClient(
            username=INVERTER_CONFIG["username"],
            password=INVERTER_CONFIG["password"],
            base_url=INVERTER_CONFIG["base_url"]
        ) as client:
            stations = await Station.load_all(client)
            if not stations:
                return None

            station = stations[0]
            inverter = None
            for inv in station.all_inverters:
                inverter = inv
                break

            if not inverter:
                return None

            await inverter.refresh()

            return {
                "pv1_voltage": inverter.pv1_voltage,
                "pv1_power": inverter.pv1_power,
                "pv2_voltage": inverter.pv2_voltage,
                "pv2_power": inverter.pv2_power,
                "pv3_voltage": inverter.pv3_voltage,
                "pv3_power": inverter.pv3_power,
                "pv_total_power": inverter.pv_total_power,
                "battery_voltage": inverter.battery_voltage,
                "battery_soc": inverter.battery_soc,
                "battery_charge_power": inverter.battery_charge_power,
                "battery_discharge_power": inverter.battery_discharge_power,
                "battery_temperature": inverter.battery_temperature,
                "grid_voltage": inverter.grid_voltage_r,
                "grid_frequency": inverter.grid_frequency,
                "power_to_grid": inverter.power_to_grid,
                "power_to_user": inverter.power_to_user,
                "consumption_power": inverter.consumption_power,
                "inverter_power": inverter.inverter_power,
                "inverter_temperature": inverter.inverter_temperature,
                "status": inverter.status_text,
            }
    except Exception as e:
        print(f"Error fetching inverter data: {e}")
        return None


def get_inverter_data_sync():
    """Synchronous wrapper for async inverter fetch."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(fetch_inverter_data())
    finally:
        loop.close()


# =============================================================================
# FLASK APP
# =============================================================================

app = Flask(__name__)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Solar Dashboard - Oakland, CA</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #fff;
            overflow: hidden;
        }
        #container { display: flex; height: 100vh; }
        #canvas-container { flex: 1; position: relative; }
        #stats-panel {
            width: 380px;
            background: rgba(0,0,0,0.7);
            backdrop-filter: blur(10px);
            padding: 20px;
            overflow-y: auto;
            border-left: 1px solid rgba(255,255,255,0.1);
        }
        h1 {
            font-size: 1.4em;
            margin-bottom: 5px;
            background: linear-gradient(90deg, #f39c12, #e74c3c);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .subtitle { color: #888; font-size: 0.85em; margin-bottom: 20px; }
        .section {
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 15px;
        }
        .section-title {
            font-size: 0.75em;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #888;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .section-title .icon { font-size: 1.2em; }
        .stat-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .stat-row:last-child { border-bottom: none; }
        .stat-label { color: #aaa; font-size: 0.9em; }
        .stat-value {
            font-weight: 600;
            font-size: 1.1em;
            font-variant-numeric: tabular-nums;
        }
        .stat-value.power { color: #f39c12; }
        .stat-value.voltage { color: #3498db; }
        .stat-value.percent { color: #2ecc71; }
        .stat-value.temp { color: #e74c3c; }
        .stat-value.good { color: #2ecc71; }
        .stat-value.warning { color: #f39c12; }
        .stat-value.bad { color: #e74c3c; }
        .mppt-detail { padding: 2px 0 8px 0; }
        .mppt-detail .stat-value { font-size: 0.85em; opacity: 0.8; }
        .big-stat {
            text-align: center;
            padding: 20px;
        }
        .big-stat .value {
            font-size: 3em;
            font-weight: 700;
            background: linear-gradient(90deg, #f39c12, #e67e22);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .big-stat .label {
            color: #888;
            font-size: 0.9em;
            margin-top: 5px;
        }
        .performance-bar {
            height: 8px;
            background: rgba(255,255,255,0.1);
            border-radius: 4px;
            overflow: hidden;
            margin-top: 10px;
        }
        .performance-bar .fill {
            height: 100%;
            background: linear-gradient(90deg, #e74c3c, #f39c12, #2ecc71);
            transition: width 0.5s ease;
        }
        .sun-info {
            display: flex;
            justify-content: space-around;
            text-align: center;
        }
        .sun-info .time-block .label { font-size: 0.75em; color: #888; }
        .sun-info .time-block .time { font-size: 1.2em; font-weight: 600; }
        .last-update {
            text-align: center;
            color: #666;
            font-size: 0.75em;
            margin-top: 10px;
        }
        #loading {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            color: #888;
        }
        .legend {
            display: flex;
            gap: 20px;
            justify-content: center;
            margin-top: 10px;
            font-size: 0.8em;
        }
        .legend-item {
            display: flex;
            align-items: center;
            gap: 5px;
        }
        .legend-color {
            width: 12px;
            height: 12px;
            border-radius: 2px;
        }
        .legend-color.sw { background: #3498db; }
        .legend-color.ne { background: #9b59b6; }
        .legend-color.yard { background: #27ae60; }
    </style>
</head>
<body>
    <div id="container">
        <div id="canvas-container">
            <div id="loading">Loading 3D scene...</div>
        </div>
        <div id="stats-panel">
            <h1>Solar Dashboard</h1>
            <div class="subtitle">Oakland, CA - Live System Monitor</div>

            <div class="section big-stat">
                <div class="value" id="total-pv">--</div>
                <div class="label">Total PV Power (W)</div>
                <div class="performance-bar">
                    <div class="fill" id="performance-fill" style="width: 0%"></div>
                </div>
                <div style="display:flex; justify-content:space-between; margin-top:5px; font-size:0.8em; color:#888;">
                    <span>0%</span>
                    <span id="performance-text">-- % of expected</span>
                    <span>100%</span>
                </div>
            </div>

            <div class="section">
                <div class="section-title"><span class="icon">☀️</span> Sun Position</div>
                <div class="stat-row">
                    <span class="stat-label">Altitude</span>
                    <span class="stat-value" id="sun-altitude">--°</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Azimuth</span>
                    <span class="stat-value" id="sun-azimuth">--°</span>
                </div>
                <div class="sun-info" style="margin-top:15px;">
                    <div class="time-block">
                        <div class="label">Sunrise</div>
                        <div class="time" id="sunrise">--:--</div>
                    </div>
                    <div class="time-block">
                        <div class="label">Sunset</div>
                        <div class="time" id="sunset">--:--</div>
                    </div>
                </div>
            </div>

            <div class="section">
                <div class="section-title"><span class="icon">⚡</span> PV Arrays</div>
                <div class="stat-row">
                    <span class="stat-label">MPPT 1</span>
                    <span class="stat-value power" id="pv1">-- W</span>
                </div>
                <div class="stat-row mppt-detail">
                    <span class="stat-label"></span>
                    <span class="stat-value voltage" id="pv1-detail">-- V / -- A</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">MPPT 2</span>
                    <span class="stat-value power" id="pv2">-- W</span>
                </div>
                <div class="stat-row mppt-detail">
                    <span class="stat-label"></span>
                    <span class="stat-value voltage" id="pv2-detail">-- V / -- A</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">MPPT 3</span>
                    <span class="stat-value power" id="pv3">-- W</span>
                </div>
                <div class="stat-row mppt-detail">
                    <span class="stat-label"></span>
                    <span class="stat-value voltage" id="pv3-detail">-- V / -- A</span>
                </div>
                <div class="legend">
                    <div class="legend-item"><div class="legend-color sw"></div> SW Roof (217°)</div>
                    <div class="legend-item"><div class="legend-color ne"></div> NE Roof (37°)</div>
                    <div class="legend-item"><div class="legend-color yard"></div> Backyard</div>
                </div>
            </div>

            <div class="section">
                <div class="section-title"><span class="icon">🔋</span> Battery</div>
                <div class="stat-row">
                    <span class="stat-label">State of Charge</span>
                    <span class="stat-value percent" id="battery-soc">-- %</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Voltage</span>
                    <span class="stat-value voltage" id="battery-voltage">-- V</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Power</span>
                    <span class="stat-value power" id="battery-power">-- W</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Temperature</span>
                    <span class="stat-value temp" id="battery-temp">-- °C</span>
                </div>
            </div>

            <div class="section">
                <div class="section-title"><span class="icon">🔌</span> Grid</div>
                <div class="stat-row">
                    <span class="stat-label">Export to Grid</span>
                    <span class="stat-value power" id="grid-export">-- W</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">To Home</span>
                    <span class="stat-value power" id="grid-import">-- W</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Voltage</span>
                    <span class="stat-value voltage" id="grid-voltage">-- V</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Frequency</span>
                    <span class="stat-value" id="grid-freq">-- Hz</span>
                </div>
            </div>

            <div class="section">
                <div class="section-title"><span class="icon">🌡️</span> Inverter</div>
                <div class="stat-row">
                    <span class="stat-label">Output Power</span>
                    <span class="stat-value power" id="inverter-power">-- W</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Temperature</span>
                    <span class="stat-value temp" id="inverter-temp">-- °C</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Status</span>
                    <span class="stat-value good" id="inverter-status">--</span>
                </div>
            </div>

            <div class="last-update">Last update: <span id="last-update">--</span></div>
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    <script>
        // Three.js Scene Setup - Optimized for performance
        let scene, camera, renderer, sun, sunLight, controls;
        let roofSW, roofNE, backyardArray;
        let swPowerLabel, nePowerLabel, yardPowerLabel, gridExportLabel;
        let batteryStatusLabel, batteryPowerLabel;
        let batteryWire;
        let gridWires = [];
        let sunData = { altitude: 0, azimuth: 180 };
        let animationId;
        let lastRenderTime = 0;
        const TARGET_FPS = 30; // Limit to 30fps
        const FRAME_TIME = 1000 / TARGET_FPS;

        const SUN_DISTANCE = 40;

        // Sun ray particles
        let sunRayParticles;
        let sunRayPositions;
        let sunRayVelocities;
        const NUM_SUN_RAYS = 60;
        let sunRayDirection = new THREE.Vector3(0, -1, 0);

        function init() {
            const container = document.getElementById('canvas-container');
            const loading = document.getElementById('loading');

            // Scene
            scene = new THREE.Scene();
            scene.background = new THREE.Color(0x1a1a2e);

            // Camera - fixed position, no rotation
            camera = new THREE.PerspectiveCamera(
                50,
                container.clientWidth / container.clientHeight,
                1,
                200
            );
            camera.position.set(30, 25, 30);
            camera.lookAt(0, 2, 0);

            // Renderer - disable antialiasing for performance
            renderer = new THREE.WebGLRenderer({ antialias: false });
            renderer.setSize(container.clientWidth, container.clientHeight);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5)); // Limit pixel ratio
            container.appendChild(renderer.domElement);
            loading.style.display = 'none';

            // OrbitControls for click-and-drag rotation
            controls = new THREE.OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            controls.dampingFactor = 0.05;
            controls.target.set(0, 2, 0);
            controls.minDistance = 15;
            controls.maxDistance = 80;
            controls.maxPolarAngle = Math.PI / 2.1; // Don't go below ground

            // Simple ambient light
            const ambient = new THREE.AmbientLight(0x6688aa, 0.6);
            scene.add(ambient);

            // Sun light - no shadows for performance
            sunLight = new THREE.DirectionalLight(0xffffee, 1.0);
            scene.add(sunLight);

            // Sun sphere - simple geometry
            const sunGeometry = new THREE.SphereGeometry(2, 16, 16);
            const sunMaterial = new THREE.MeshBasicMaterial({ color: 0xffdd44 });
            sun = new THREE.Mesh(sunGeometry, sunMaterial);
            scene.add(sun);

            // Sun ray lines - streaming from sun to roof (each ray = 2 points for a line segment)
            const rayGeometry = new THREE.BufferGeometry();
            sunRayPositions = new Float32Array(NUM_SUN_RAYS * 6); // 2 points per ray, 3 coords each
            sunRayVelocities = [];

            // Initialize all rays at origin - will be positioned properly on first sun update
            for (let i = 0; i < NUM_SUN_RAYS; i++) {
                // Start point
                sunRayPositions[i * 6] = 0;
                sunRayPositions[i * 6 + 1] = 50; // High up, will be set by sun position
                sunRayPositions[i * 6 + 2] = 0;
                // End point (slightly behind start to create line)
                sunRayPositions[i * 6 + 3] = 0;
                sunRayPositions[i * 6 + 4] = 52;
                sunRayPositions[i * 6 + 5] = 0;

                sunRayVelocities.push({
                    speed: 0.2 + Math.random() * 0.15,
                    offsetX: (Math.random() - 0.5) * 8, // Spread around sun
                    offsetZ: (Math.random() - 0.5) * 8,
                    t: Math.random() // Random start position along path
                });
            }

            rayGeometry.setAttribute('position', new THREE.BufferAttribute(sunRayPositions, 3));

            const rayMaterial = new THREE.LineBasicMaterial({
                color: 0xffee66,
                transparent: true,
                opacity: 0.4,
                blending: THREE.AdditiveBlending
            });

            sunRayParticles = new THREE.LineSegments(rayGeometry, rayMaterial);
            sunRayParticles.visible = false; // Hidden until sun is up
            scene.add(sunRayParticles);

            // Ground - simple plane
            const groundGeometry = new THREE.PlaneGeometry(80, 80);
            const groundMaterial = new THREE.MeshLambertMaterial({ color: 0x3d6b35 });
            const ground = new THREE.Mesh(groundGeometry, groundMaterial);
            ground.rotation.x = -Math.PI / 2;
            ground.position.y = 0;
            scene.add(ground);

            // Simple grid
            const gridHelper = new THREE.GridHelper(80, 20, 0x444444, 0x333333);
            scene.add(gridHelper);

            // Create house with proper roof orientation
            createHouse();

            // Compass markers
            createCompass();

            // Handle resize
            window.addEventListener('resize', onWindowResize);

            // Start animation loop (throttled)
            animate();

            // Start data polling
            fetchData();
            setInterval(fetchData, 5000);
        }

        function createHouse() {
            // House dimensions: 80ft x 20ft = scale to ~24 x 6 units
            // Ridge runs SE-NW (127° azimuth), so house long axis is along ridge
            const houseLength = 24;  // 80ft scaled
            const houseWidth = 6;    // 20ft scaled
            const houseHeight = 4;
            const ridgeAzimuth = 127; // SE-NW (perpendicular to panel faces)
            const ridgeRad = ridgeAzimuth * Math.PI / 180;
            const tiltAngle = 20 * Math.PI / 180; // 20° roof pitch

            // House base - oriented along ridge direction
            const houseGeometry = new THREE.BoxGeometry(houseLength, houseHeight, houseWidth);
            const houseMaterial = new THREE.MeshLambertMaterial({ color: 0x8b7355 });
            const house = new THREE.Mesh(houseGeometry, houseMaterial);
            house.position.set(0, houseHeight / 2, 0);
            house.rotation.y = -ridgeRad; // Align with ridge
            scene.add(house);

            // Roof calculations
            const roofRun = houseWidth / 2; // Half width for each side
            const roofRise = roofRun * Math.tan(tiltAngle);
            const roofSlopeLength = roofRun / Math.cos(tiltAngle);
            const ridgeHeight = houseHeight + roofRise;

            // Create roof group to rotate together
            const roofGroup = new THREE.Group();
            roofGroup.rotation.y = -ridgeRad;

            // SW facing roof (left side when looking from SE)
            const roofSWGeometry = new THREE.PlaneGeometry(houseLength, roofSlopeLength);
            const roofSWMaterial = new THREE.MeshLambertMaterial({
                color: 0x3498db,
                side: THREE.DoubleSide
            });
            roofSW = new THREE.Mesh(roofSWGeometry, roofSWMaterial);
            roofSW.rotation.x = Math.PI / 2 - tiltAngle;
            roofSW.position.set(0, houseHeight + roofRise / 2, -roofRun / 2);
            roofGroup.add(roofSW);

            // NE facing roof (right side when looking from SE)
            const roofNEGeometry = new THREE.PlaneGeometry(houseLength, roofSlopeLength);
            const roofNEMaterial = new THREE.MeshLambertMaterial({
                color: 0x9b59b6,
                side: THREE.DoubleSide
            });
            roofNE = new THREE.Mesh(roofNEGeometry, roofNEMaterial);
            roofNE.rotation.x = -(Math.PI / 2 - tiltAngle);
            roofNE.position.set(0, houseHeight + roofRise / 2, roofRun / 2);
            roofGroup.add(roofNE);

            // Ridge cap
            const ridgeGeometry = new THREE.BoxGeometry(houseLength, 0.3, 0.4);
            const ridgeMaterial = new THREE.MeshLambertMaterial({ color: 0x555555 });
            const ridge = new THREE.Mesh(ridgeGeometry, ridgeMaterial);
            ridge.position.set(0, ridgeHeight, 0);
            roofGroup.add(ridge);

            scene.add(roofGroup);

            // Add panel grid lines (offset to visible top surface)
            addPanelGrid(roofSW, 0x2980b9, 12, 3, -0.1);  // Negative Z for SW top surface
            addPanelGrid(roofNE, 0x7d3c98, 12, 3, 0.1);   // Positive Z for NE top surface

            // Power labels on roof panels - positioned over center of each roof face
            // Roof local coords: SW at z=-5, NE at z=+5, rotated by -127° around Y
            // After rotation: SW center ≈ (4, y, 3), NE center ≈ (-4, y, -3)
            const labelHeight = 6;  // Just above the roof

            // SW roof label (MPPT2 - blue face) - at world coords matching rotated local z=-5
            swPowerLabel = createPowerLabel('0W');
            swPowerLabel.position.set(4, labelHeight, 3);
            scene.add(swPowerLabel);

            // NE roof label (MPPT1 - purple face) - at world coords matching rotated local z=+5
            nePowerLabel = createPowerLabel('0W');
            nePowerLabel.position.set(-4, labelHeight, -3);
            scene.add(nePowerLabel);

            // Backyard array - small ground-mounted array
            const backyardGeometry = new THREE.PlaneGeometry(6, 4);
            const backyardMaterial = new THREE.MeshLambertMaterial({
                color: 0x27ae60,
                side: THREE.DoubleSide
            });
            backyardArray = new THREE.Mesh(backyardGeometry, backyardMaterial);

            // Position in backyard - well away from house
            backyardArray.position.set(18, 2.5, -12);
            // Tilt toward South (180°) at 30° angle - MPPT3
            backyardArray.rotation.order = 'YXZ';
            backyardArray.rotation.y = 0;  // Face south (180° = toward +Z after rotation)
            backyardArray.rotation.x = -30 * Math.PI / 180;
            scene.add(backyardArray);

            // Add grid to backyard array
            addPanelGrid(backyardArray, 0x1e8449, 6, 4, 0.1);

            // Power label on backyard array - above the panel
            yardPowerLabel = createPowerLabel('0W');
            yardPowerLabel.position.set(0, 2, 1);
            backyardArray.add(yardPowerLabel);

            // Create grid service drop (utility pole with meter)
            createGridService();
        }

        function createPowerLabel(text) {
            const canvas = document.createElement('canvas');
            canvas.width = 256;
            canvas.height = 128;
            const ctx = canvas.getContext('2d');

            const texture = new THREE.CanvasTexture(canvas);
            const material = new THREE.SpriteMaterial({ map: texture, transparent: true });
            const sprite = new THREE.Sprite(material);
            sprite.scale.set(4, 2, 1);
            sprite.userData = { canvas, ctx, texture };
            updatePowerLabel(sprite, text);
            return sprite;
        }

        function updatePowerLabel(sprite, text) {
            const { canvas, ctx, texture } = sprite.userData;
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            // Background
            ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
            ctx.roundRect(10, 20, canvas.width - 20, canvas.height - 40, 10);
            ctx.fill();

            // Text
            ctx.fillStyle = '#f39c12';
            ctx.font = 'bold 48px Arial';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(text, canvas.width / 2, canvas.height / 2);

            texture.needsUpdate = true;
        }

        function formatPower(watts) {
            return watts.toLocaleString() + 'W';
        }

        function createGridService() {
            // Utility pole
            const poleGeometry = new THREE.CylinderGeometry(0.2, 0.3, 12, 8);
            const poleMaterial = new THREE.MeshLambertMaterial({ color: 0x4a3728 });
            const pole = new THREE.Mesh(poleGeometry, poleMaterial);
            pole.position.set(-18, 6, 10);
            scene.add(pole);

            // Crossarm
            const crossarmGeometry = new THREE.BoxGeometry(6, 0.3, 0.3);
            const crossarm = new THREE.Mesh(crossarmGeometry, poleMaterial);
            crossarm.position.set(-18, 11, 10);
            scene.add(crossarm);

            // Insulators
            const insulatorGeometry = new THREE.CylinderGeometry(0.15, 0.2, 0.5, 8);
            const insulatorMaterial = new THREE.MeshLambertMaterial({ color: 0x888888 });
            [-2, 0, 2].forEach(offset => {
                const insulator = new THREE.Mesh(insulatorGeometry, insulatorMaterial);
                insulator.position.set(-18 + offset, 11.4, 10);
                scene.add(insulator);
            });

            // Meter box on house
            const meterGeometry = new THREE.BoxGeometry(1, 1.5, 0.5);
            const meterMaterial = new THREE.MeshLambertMaterial({ color: 0x666666 });
            const meter = new THREE.Mesh(meterGeometry, meterMaterial);
            meter.position.set(-10, 3, 6);
            scene.add(meter);

            // Service drop wires from pole to meter
            const wireMaterial = new THREE.LineBasicMaterial({ color: 0x222222, linewidth: 2 });
            const wirePoints = [
                new THREE.Vector3(-18, 11, 10),
                new THREE.Vector3(-14, 9, 8),
                new THREE.Vector3(-10, 4, 6)
            ];
            const wireCurve = new THREE.CatmullRomCurve3(wirePoints);
            const wireGeometry = new THREE.BufferGeometry().setFromPoints(wireCurve.getPoints(20));
            const wire = new THREE.Line(wireGeometry, wireMaterial);
            scene.add(wire);
            gridWires.push({ curve: wireCurve, mesh: wire });

            // Grid export label (animated along wire)
            gridExportLabel = createPowerLabel('0W');
            gridExportLabel.scale.set(3, 1.5, 1);
            scene.add(gridExportLabel);

            // Battery bank - positioned near the meter/inverter
            const batteryGeometry = new THREE.BoxGeometry(2.5, 3, 1.5);
            const batteryMaterial = new THREE.MeshLambertMaterial({ color: 0x2ecc71 });
            const battery = new THREE.Mesh(batteryGeometry, batteryMaterial);
            battery.position.set(-14, 1.5, 6);
            scene.add(battery);

            // Battery terminal strip on top
            const terminalGeometry = new THREE.BoxGeometry(1.5, 0.2, 0.8);
            const terminalMaterial = new THREE.MeshLambertMaterial({ color: 0x333333 });
            const terminal = new THREE.Mesh(terminalGeometry, terminalMaterial);
            terminal.position.set(-14, 3.1, 6);
            scene.add(terminal);

            // Battery status label (voltage & SOC %) - static above battery
            batteryStatusLabel = createPowerLabel('0V 0%');
            batteryStatusLabel.scale.set(3, 1.5, 1);
            batteryStatusLabel.position.set(-14, 5, 6);
            scene.add(batteryStatusLabel);

            // Wire from battery to meter/inverter
            const batteryWireMaterial = new THREE.LineBasicMaterial({ color: 0xcc0000, linewidth: 2 });
            const batteryWirePoints = [
                new THREE.Vector3(-14, 3, 6),  // Battery top
                new THREE.Vector3(-12, 3.5, 6), // Midpoint
                new THREE.Vector3(-10, 3, 6)   // Meter box
            ];
            const batteryWireCurve = new THREE.CatmullRomCurve3(batteryWirePoints);
            const batteryWireGeometry = new THREE.BufferGeometry().setFromPoints(batteryWireCurve.getPoints(15));
            const batteryWireMesh = new THREE.Line(batteryWireGeometry, batteryWireMaterial);
            scene.add(batteryWireMesh);
            batteryWire = { curve: batteryWireCurve, mesh: batteryWireMesh };

            // Battery power label (animated along wire)
            batteryPowerLabel = createPowerLabel('0W');
            batteryPowerLabel.scale.set(2.5, 1.25, 1);
            batteryPowerLabel.visible = false;
            scene.add(batteryPowerLabel);
        }

        function addPanelGrid(roof, color, cols = 12, rows = 3, zOffset = 0.1) {
            const lines = new THREE.Group();
            const mat = new THREE.LineBasicMaterial({ color: color });

            const halfWidth = cols / 2;
            const halfHeight = rows / 2;

            // Horizontal lines
            for (let i = -rows; i <= rows; i++) {
                const h = [
                    new THREE.Vector3(-halfWidth, i * (halfHeight / rows), zOffset),
                    new THREE.Vector3(halfWidth, i * (halfHeight / rows), zOffset)
                ];
                lines.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(h), mat));
            }
            // Vertical lines
            for (let i = -cols; i <= cols; i++) {
                const v = [
                    new THREE.Vector3(i * (halfWidth / cols), -halfHeight, zOffset),
                    new THREE.Vector3(i * (halfWidth / cols), halfHeight, zOffset)
                ];
                lines.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(v), mat));
            }
            roof.add(lines);
        }

        function createCompass() {
            const addLabel = (text, angle, color) => {
                const canvas = document.createElement('canvas');
                canvas.width = 64;
                canvas.height = 64;
                const ctx = canvas.getContext('2d');
                ctx.fillStyle = color;
                ctx.font = 'bold 48px Arial';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(text, 32, 32);

                const texture = new THREE.CanvasTexture(canvas);
                const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture }));
                sprite.scale.set(4, 4, 1);
                const rad = angle * Math.PI / 180;
                sprite.position.set(Math.sin(rad) * 35, 1, -Math.cos(rad) * 35);
                scene.add(sprite);
            };

            addLabel('N', 0, '#e74c3c');
            addLabel('E', 90, '#888888');
            addLabel('S', 180, '#888888');
            addLabel('W', 270, '#888888');
        }

        function updateSunPosition(altitude, azimuth) {
            const altRad = altitude * Math.PI / 180;
            const azRad = azimuth * Math.PI / 180;

            const x = SUN_DISTANCE * Math.cos(altRad) * Math.sin(azRad);
            const y = SUN_DISTANCE * Math.sin(altRad);
            const z = -SUN_DISTANCE * Math.cos(altRad) * Math.cos(azRad);

            sun.position.set(x, Math.max(y, -5), z);
            sunLight.position.copy(sun.position);

            // Update sun ray direction (from sun toward roof/origin)
            sunRayDirection.set(-x, -y, -z).normalize();

            if (altitude > 0) {
                sun.visible = true;
                sunRayParticles.visible = true;
                sunLight.intensity = Math.min(1.2, 0.3 + altitude / 30);
                const hue = 0.12 - (Math.max(0, 15 - altitude) / 15) * 0.06;
                sun.material.color.setHSL(hue, 1, 0.6);
                // Adjust ray opacity based on sun altitude
                sunRayParticles.material.opacity = Math.min(0.6, altitude / 60);
            } else {
                sun.visible = false;
                sunRayParticles.visible = false;
                sunLight.intensity = 0.2;
            }

            updateRoofBrightness(altitude, azimuth);
        }

        function updateRoofBrightness(alt, az) {
            if (alt <= 0) {
                roofSW.material.emissive = new THREE.Color(0x000000);
                roofNE.material.emissive = new THREE.Color(0x000000);
                return;
            }

            // Calculate facing factor for each roof
            const swDiff = Math.abs(az - 217);
            const neDiff = Math.abs(az - 37);
            const swFace = Math.max(0, 1 - Math.min(swDiff, 360 - swDiff) / 90);
            const neFace = Math.max(0, 1 - Math.min(neDiff, 360 - neDiff) / 90);

            const swBright = swFace * (alt / 50) * 0.4;
            const neBright = neFace * (alt / 50) * 0.4;

            roofSW.material.emissive = new THREE.Color(swBright * 0.2, swBright * 0.5, swBright);
            roofNE.material.emissive = new THREE.Color(neBright * 0.5, neBright * 0.2, neBright);
        }

        function onWindowResize() {
            const container = document.getElementById('canvas-container');
            camera.aspect = container.clientWidth / container.clientHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(container.clientWidth, container.clientHeight);
        }

        let gridExportT = 0;
        let currentGridExport = 0;
        let batteryPowerT = 0;
        let currentBatteryPower = 0; // Positive = charging, negative = discharging

        function animate(currentTime) {
            animationId = requestAnimationFrame(animate);

            // Throttle to target FPS
            if (currentTime - lastRenderTime < FRAME_TIME) return;
            lastRenderTime = currentTime;

            // Animate grid export label along wire (from house to pole)
            if (gridWires.length > 0 && gridExportLabel && currentGridExport > 0) {
                gridExportT = (gridExportT + 0.012) % 1;
                // Reverse direction: 1-t goes from house (end) to pole (start)
                const pos = gridWires[0].curve.getPoint(1 - gridExportT);
                gridExportLabel.position.copy(pos);
                gridExportLabel.position.y += 2; // Offset above wire
                gridExportLabel.visible = true;
            } else if (gridExportLabel) {
                gridExportLabel.visible = false;
            }

            // Animate battery power label along wire
            if (batteryWire && batteryPowerLabel && currentBatteryPower !== 0) {
                batteryPowerT = (batteryPowerT + 0.015) % 1;
                // Direction based on charge/discharge:
                // Charging (positive): power flows from inverter TO battery (t goes 1->0)
                // Discharging (negative): power flows from battery TO inverter (t goes 0->1)
                const t = currentBatteryPower > 0 ? (1 - batteryPowerT) : batteryPowerT;
                const pos = batteryWire.curve.getPoint(t);
                batteryPowerLabel.position.copy(pos);
                batteryPowerLabel.position.y += 1.5; // Offset above wire
                batteryPowerLabel.visible = true;
            } else if (batteryPowerLabel) {
                batteryPowerLabel.visible = false;
            }

            // Animate sun ray lines streaming from sun to roof
            if (sunRayParticles && sunRayParticles.visible && sunRayPositions && sun.visible) {
                const positions = sunRayParticles.geometry.attributes.position.array;
                const rayLength = 3; // Length of each light ray line

                for (let i = 0; i < NUM_SUN_RAYS; i++) {
                    const vel = sunRayVelocities[i];

                    // Advance t (position along sun-to-roof path)
                    vel.t += vel.speed * 0.02;

                    // Reset if ray reached the roof
                    if (vel.t > 1) {
                        vel.t = 0;
                        vel.offsetX = (Math.random() - 0.5) * 10;
                        vel.offsetZ = (Math.random() - 0.5) * 10;
                    }

                    // Interpolate from sun to roof (0,5,0)
                    const t = vel.t;
                    const startX = sun.position.x * (1 - t) + vel.offsetX * t;
                    const startY = sun.position.y * (1 - t) + 5 * t;
                    const startZ = sun.position.z * (1 - t) + vel.offsetZ * t;

                    // End point slightly behind (toward sun) to create line
                    const t2 = Math.max(0, t - 0.05);
                    const endX = sun.position.x * (1 - t2) + vel.offsetX * t2;
                    const endY = sun.position.y * (1 - t2) + 5 * t2;
                    const endZ = sun.position.z * (1 - t2) + vel.offsetZ * t2;

                    // Update line segment positions
                    positions[i * 6] = startX;
                    positions[i * 6 + 1] = startY;
                    positions[i * 6 + 2] = startZ;
                    positions[i * 6 + 3] = endX;
                    positions[i * 6 + 4] = endY;
                    positions[i * 6 + 5] = endZ;
                }
                sunRayParticles.geometry.attributes.position.needsUpdate = true;
            }

            controls.update();
            renderer.render(scene, camera);
        }

        // Data fetching and UI updates
        async function fetchData() {
            try {
                const response = await fetch('/api/data');
                const data = await response.json();

                // Update sun position
                if (data.sun) {
                    updateSunPosition(data.sun.altitude, data.sun.azimuth);
                    document.getElementById('sun-altitude').textContent = data.sun.altitude.toFixed(1) + '°';
                    document.getElementById('sun-azimuth').textContent = data.sun.azimuth.toFixed(1) + '°';
                    document.getElementById('sunrise').textContent = formatTime(data.sun.sunrise_hour);
                    document.getElementById('sunset').textContent = formatTime(data.sun.sunset_hour);
                }

                // Update inverter data
                if (data.inverter) {
                    const inv = data.inverter;
                    document.getElementById('total-pv').textContent = inv.pv_total_power.toLocaleString();

                    // MPPT 1
                    document.getElementById('pv1').textContent = formatPower(inv.pv1_power);
                    const pv1Amps = inv.pv1_voltage > 0 ? (inv.pv1_power / inv.pv1_voltage).toFixed(1) : '0.0';
                    document.getElementById('pv1-detail').textContent = `${inv.pv1_voltage.toFixed(1)}V / ${pv1Amps}A`;

                    // MPPT 2
                    document.getElementById('pv2').textContent = formatPower(inv.pv2_power);
                    const pv2Amps = inv.pv2_voltage > 0 ? (inv.pv2_power / inv.pv2_voltage).toFixed(1) : '0.0';
                    document.getElementById('pv2-detail').textContent = `${inv.pv2_voltage.toFixed(1)}V / ${pv2Amps}A`;

                    // MPPT 3
                    document.getElementById('pv3').textContent = formatPower(inv.pv3_power);
                    const pv3Amps = inv.pv3_voltage > 0 ? (inv.pv3_power / inv.pv3_voltage).toFixed(1) : '0.0';
                    document.getElementById('pv3-detail').textContent = `${inv.pv3_voltage.toFixed(1)}V / ${pv3Amps}A`;

                    document.getElementById('battery-soc').textContent = inv.battery_soc + '%';
                    document.getElementById('battery-voltage').textContent = inv.battery_voltage.toFixed(1) + 'V';

                    const battPower = inv.battery_charge_power - inv.battery_discharge_power;
                    document.getElementById('battery-power').textContent =
                        (battPower >= 0 ? '+' : '') + battPower.toLocaleString() + 'W';
                    document.getElementById('battery-temp').textContent = inv.battery_temperature + '°C';

                    document.getElementById('grid-export').textContent = formatPower(inv.power_to_grid);
                    document.getElementById('grid-import').textContent = formatPower(inv.consumption_power);
                    document.getElementById('grid-voltage').textContent = inv.grid_voltage.toFixed(1) + 'V';
                    document.getElementById('grid-freq').textContent = inv.grid_frequency.toFixed(2) + 'Hz';

                    document.getElementById('inverter-power').textContent = formatPower(inv.inverter_power);
                    document.getElementById('inverter-temp').textContent = inv.inverter_temperature + '°C';
                    document.getElementById('inverter-status').textContent = inv.status;

                    // Update 3D power labels on arrays - match sidebar values exactly
                    // MPPT1 = NE face (purple)
                    // MPPT2 = SW face (blue)
                    // MPPT3 = Backyard (green, facing S)
                    if (nePowerLabel) updatePowerLabel(nePowerLabel, formatPower(inv.pv1_power));
                    if (swPowerLabel) updatePowerLabel(swPowerLabel, formatPower(inv.pv2_power));
                    if (yardPowerLabel) updatePowerLabel(yardPowerLabel, formatPower(inv.pv3_power));

                    // Update grid export animation
                    currentGridExport = inv.power_to_grid;
                    if (gridExportLabel) {
                        updatePowerLabel(gridExportLabel, formatPower(inv.power_to_grid));
                    }

                    // Update battery 3D labels
                    const batteryNetPower = inv.battery_charge_power - inv.battery_discharge_power;
                    currentBatteryPower = batteryNetPower;

                    // Static label above battery: voltage & SOC
                    if (batteryStatusLabel) {
                        updatePowerLabel(batteryStatusLabel, inv.battery_voltage.toFixed(1) + 'V ' + inv.battery_soc + '%');
                    }

                    // Animated power label along wire
                    if (batteryPowerLabel && batteryNetPower !== 0) {
                        const prefix = batteryNetPower > 0 ? '+' : '';
                        updatePowerLabel(batteryPowerLabel, prefix + Math.abs(batteryNetPower).toLocaleString() + 'W');
                    }
                }

                // Update performance
                if (data.expected_power && data.inverter) {
                    const expected = data.expected_power;
                    const actual = data.inverter.pv_total_power;
                    const performance = expected > 0 ? (actual / expected * 100) : 0;

                    document.getElementById('performance-fill').style.width = Math.min(100, performance) + '%';
                    document.getElementById('performance-text').textContent =
                        performance.toFixed(0) + '% of ' + expected.toFixed(0) + 'W expected';
                }

                document.getElementById('last-update').textContent = new Date().toLocaleTimeString();

            } catch (error) {
                console.error('Error fetching data:', error);
            }
        }

        function formatTime(hour) {
            if (hour === null || hour === undefined) return '--:--';
            const h = Math.floor(hour);
            const m = Math.floor((hour - h) * 60);
            return h.toString().padStart(2, '0') + ':' + m.toString().padStart(2, '0');
        }

        // Initialize
        init();
    </script>
</body>
</html>
'''


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/data')
def get_data():
    """API endpoint returning all live data."""
    now = datetime.now(TIMEZONE)

    # Calculate sun position
    sun_pos = calculate_solar_position(now, LATITUDE, LONGITUDE)

    # Calculate expected power
    dni = calculate_clear_sky_dni(sun_pos["altitude"])
    total_irradiance = 0
    for face in ROOF_FACES:
        irr = calculate_panel_irradiance(
            sun_pos["altitude"], sun_pos["azimuth"],
            PANEL_TILT, face["azimuth"], dni
        )
        total_irradiance += irr * face["fraction"]

    expected_power = ARRAY_SIZE_KW * 1000 * (total_irradiance / 1000) * 0.85

    # Get inverter data (cached or fresh)
    inverter_data = get_inverter_data_sync()

    return jsonify({
        "timestamp": now.isoformat(),
        "sun": {
            "altitude": sun_pos["altitude"],
            "azimuth": sun_pos["azimuth"],
            "sunrise_hour": sun_pos["sunrise_hour"],
            "sunset_hour": sun_pos["sunset_hour"],
            "is_daylight": sun_pos["is_daylight"],
        },
        "expected_power": expected_power,
        "dni": dni,
        "inverter": inverter_data,
    })


if __name__ == '__main__':
    print("\n" + "="*60)
    print("  Solar Dashboard - 3D Visualization")
    print("="*60)
    print(f"  Location: Oakland, CA ({LATITUDE}°N, {LONGITUDE}°W)")
    print(f"  Array: {ARRAY_SIZE_KW}kW (SW 217° + NE 37°)")
    print("="*60)
    print("\n  Open in browser: http://localhost:5050\n")

    app.run(host='0.0.0.0', port=5050, debug=False)
