# How to Collect Device Data for Unsupported Inverters

This guide walks you through collecting data from your Luxpower/EG4 inverter so developers can add support for your inverter model.

**The process is simple:**
1. Choose your method (download executable OR use browser)
2. Run one command with your login credentials
3. Upload the generated zip file to GitHub

## What You'll Need

- **Your EG4/Luxpower web portal login** (the same username and password you use at monitor.eg4electronics.com)
- **5-10 minutes** (the tool automatically discovers and scans all your devices)

---

## Choose Your Method

### Option A: Download Executable (Easiest - No Installation Required)

Download a ready-to-run program for your operating system:

| Operating System | Download Link |
|------------------|---------------|
| **Windows** | [pylxpweb-collect-windows.exe](https://github.com/joyfulhouse/pylxpweb/releases/latest/download/pylxpweb-collect-windows.exe) |
| **Mac** | [pylxpweb-collect-macos](https://github.com/joyfulhouse/pylxpweb/releases/latest/download/pylxpweb-collect-macos) |
| **Linux** | [pylxpweb-collect-linux](https://github.com/joyfulhouse/pylxpweb/releases/latest/download/pylxpweb-collect-linux) |

Then skip to [Step 3: Run the Data Collection](#step-3-run-the-data-collection).

### Option B: Use GitHub Codespaces (No Download Required)

Run everything in your browser using GitHub Codespaces:

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/joyfulhouse/pylxpweb?quickstart=1)

1. Click the button above (requires free GitHub account)
2. Wait ~1 minute for the environment to start
3. In the terminal that appears, run:
   ```
   pylxpweb-collect -u YOUR_EMAIL -p YOUR_PASSWORD
   ```
4. Download the generated zip file from the file explorer on the left

### Option C: Install with Python (For developers)

If you prefer to install Python, continue with the steps below.

---

## Step 1: Install Python (Option C only)

### Windows

1. Go to https://www.python.org/downloads/
2. Click the big yellow **"Download Python"** button
3. Run the downloaded installer
4. **IMPORTANT**: Check the box that says **"Add Python to PATH"** at the bottom of the installer window
5. Click **"Install Now"**

### Mac

1. Open **Terminal** (press Cmd+Space, type "Terminal", press Enter)
2. Type this command and press Enter:
   ```
   python3 --version
   ```
3. If you see a version number like "Python 3.12.0", you're good to go!
4. If not, go to https://www.python.org/downloads/ and download the Mac installer

### Linux

Python is usually pre-installed. Open a terminal and verify:
```
python3 --version
```

---

## Step 2: Install the pylxpweb Tool

Open a command prompt or terminal:

- **Windows**: Press the Windows key, type "cmd", press Enter
- **Mac**: Press Cmd+Space, type "Terminal", press Enter
- **Linux**: Open your terminal application

Then type this command and press Enter:

```
pip install pylxpweb
```

If that doesn't work, try:
```
pip3 install pylxpweb
```

You should see some text scroll by ending with "Successfully installed pylxpweb"

---

## Step 3: Run the Data Collection

### If you downloaded the executable (Option A):

**Windows:** Open Command Prompt, navigate to your Downloads folder, and run:
```
pylxpweb-collect-windows.exe -u YOUR_EMAIL -p YOUR_PASSWORD
```

**Mac:** Open Terminal, navigate to your Downloads folder, and run:
```
chmod +x pylxpweb-collect-macos
./pylxpweb-collect-macos -u YOUR_EMAIL -p YOUR_PASSWORD
```

### If you installed with pip (Option C):

```
pylxpweb-collect -u YOUR_EMAIL -p YOUR_PASSWORD
```

**Example:**
```
pylxpweb-collect -u john.doe@email.com -p MySecretPass123
```

### For Different Regions

**EU Luxpower portal users** (eu.luxpowertek.com):
```
pylxpweb-collect -u YOUR_EMAIL -p YOUR_PASSWORD -b https://eu.luxpowertek.com
```

**US Luxpower portal users** (us.luxpowertek.com):
```
pylxpweb-collect -u YOUR_EMAIL -p YOUR_PASSWORD -b https://us.luxpowertek.com
```

### Privacy Option: Sanitize Serial Numbers

If you want to mask your serial numbers and other sensitive data before sharing:
```
pylxpweb-collect -u YOUR_EMAIL -p YOUR_PASSWORD --sanitize
```

Or use the short flag `-S`:
```
pylxpweb-collect -u YOUR_EMAIL -p YOUR_PASSWORD -S
```

This replaces serial numbers like `4512670118` with `45******18` in the output files.

---

## Step 4: Wait for Collection to Complete

The tool will automatically:
1. Log in to your account
2. Find all your inverters
3. Read all the register values from each device
4. Create report files and bundle them into a zip

This typically takes **2-10 minutes** depending on how many devices you have.

You'll see output like this:

```
======================================================================
  pylxpweb Device Data Collection Tool
  Version: 0.3.17
======================================================================

Base URL: https://monitor.eg4electronics.com
Output Directory: /Users/you/

Discovering devices in your account...

Found 2 device(s):
  1. EG4-18KPV (4512670118) - Online
  2. Grid Boss (4524850115) - Online

[1/2] Processing: EG4-18KPV
  Serial: 4512670118
  Status: Online
    Register ranges: 1
      - 0 to 366
    Scanning range 1/1...
      Mapping registers 0 to 366
        Register    0: Block size= 2,  12 params
        Register    2: Block size= 5,   1 params
        ...
    Writing EG418KPV_4512670118.json...
    Writing EG418KPV_4512670118.md...
  Done!

[2/2] Processing: Grid Boss
  ...

Creating zip archive...
  Created: pylxpweb_device_data_20251125_143022.zip

======================================================================
  Collection Complete!
======================================================================

Files created in: /Users/you/

  ZIP FILE (attach this):
    >>> pylxpweb_device_data_20251125_143022.zip <<<

  Individual files (included in zip):
    - EG418KPV_4512670118.json
    - EG418KPV_4512670118.md
    - GridBoss_4524850115.json
    - GridBoss_4524850115.md
```

---

## Step 5: Upload the Zip File to GitHub

After the collection completes, you'll have a single zip file to upload:

```
======================================================================
  UPLOAD INSTRUCTIONS - Please read carefully!
======================================================================

To request support for your inverter model(s), please:

1. Create a new GitHub issue at:
   https://github.com/joyfulhouse/pylxpweb/issues/new

2. Use a title like: "Add support for [Your Inverter Model]"

3. In the issue description, include:
   - Your inverter model name and firmware version
   - Any specific features or functions you need supported
   - Whether this is a hybrid, grid-tie, or off-grid inverter

4. ATTACH this zip file to the issue:
   >>> pylxpweb_device_data_20251125_143022.zip <<<

   The zip contains these files:
     - EG418KPV_4512670118.json
     - EG418KPV_4512670118.md
     - GridBoss_4524850115.json
     - GridBoss_4524850115.md
```

### How to Create a GitHub Issue

1. Go to https://github.com/joyfulhouse/pylxpweb/issues/new
2. If you don't have a GitHub account, click **"Sign up"** to create one (it's free)
3. Fill in the **Title** (e.g., "Add support for EG4-18KPV inverter")
4. In the description box, tell us:
   - Your inverter model
   - What features you need (battery control, grid export limits, etc.)
5. **Drag and drop the zip file** into the description box
6. Click **"Submit new issue"**

---

## Troubleshooting

### "pylxpweb-collect is not recognized"

This means Python isn't in your system PATH. Try running it this way instead:

**Windows:**
```
python -m pylxpweb.cli.collect_device_data -u YOUR_EMAIL -p YOUR_PASSWORD
```

**Mac/Linux:**
```
python3 -m pylxpweb.cli.collect_device_data -u YOUR_EMAIL -p YOUR_PASSWORD
```

### "Authentication failed" or "Invalid credentials"

- Double-check your username (email) and password
- Make sure you're using the correct portal:
  - EG4 users: No `-b` flag needed (default)
  - EU Luxpower: Add `-b https://eu.luxpowertek.com`
  - US Luxpower: Add `-b https://us.luxpowertek.com`
- Try logging into the web portal directly to verify your credentials work

### "No devices found"

- Your account may not have any devices registered
- Try logging into the web portal to confirm you can see your devices there

### "No data - stopping scan"

This is **normal**! It just means the tool reached the end of your inverter's register space. The collection should still complete successfully.

### "Connection error" or "Timeout"

- Check your internet connection
- The EG4/Luxpower servers may be temporarily unavailable
- Wait a few minutes and try again

### Where are my files?

The files are saved in the folder where you ran the command.

**Windows:** Usually `C:\Users\YourName\`

**Mac/Linux:** Usually `/Users/YourName/` or `/home/YourName/`

To save files to a specific folder, use the `-o` option:
```
pylxpweb-collect -u YOUR_EMAIL -p YOUR_PASSWORD -o C:\MyFolder
```

---

## Privacy Note

The generated files contain:
- Your inverter's serial number (can be masked with `--sanitize`)
- Register values and parameter names
- Device type information

They do **NOT** contain:
- Your username or password
- Your home address
- Personal information

**Recommended**: Use the `--sanitize` flag to automatically mask serial numbers:
```
pylxpweb-collect -u YOUR_EMAIL -p YOUR_PASSWORD --sanitize
```

This replaces serial numbers like `4512670118` with `45******18` throughout the output files, making them safe to share publicly.

---

## Questions?

- **Start a discussion**: https://github.com/joyfulhouse/pylxpweb/discussions
- **Report an issue**: https://github.com/joyfulhouse/pylxpweb/issues
