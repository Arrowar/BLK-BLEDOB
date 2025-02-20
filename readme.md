# BLK-BLEDOB Controller

![Application Interface](Data\01.png)

## Features ✨

- **BLE Device Scanning** - Discover compatible LED devices with automatic protocol detection
- **Secure Connection Management** - Establish and maintain reliable Bluetooth connections with one-click
- **Advanced LED Controls** - Comprehensive control suite including instant power switching, precise color selection through HEX/RGB inputs, and smooth brightness adjustment with 0-100% range
- **Smart Memory System** - Persistent storage of user preferences including selected colors, brightness levels, power states, and window positions

## System Requirements 💻

- **Operating System**: Windows 10/11
- **Bluetooth**: Version 4.0+

## Installation ⚙️

1. **Clone repository**:
```bash
git clone https://github.com/Arrowar/BLK-BLEDOB.git
cd BLK-BLEDOB-Controller
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

## Usage 🚀

Launch the application:
```bash
python app.py
```

### First-Time Setup

1. Click the "Scan Devices" button (magnifying glass icon)
2. Select your BLK-BLEDOB device from the discovered devices list
3. Click "Connect" (plug icon)
4. Use the control panel:
   - 🟢 Power button: Toggle device ON/OFF
   - 🎨 Color circle: Access color picker with HEX/RGB input
   - 🌞 Slider: Fine-tune brightness level

## Building Executable 📦

1. **Install PyInstaller**:
```bash
pip install pyinstaller
```

2. **Generate executable**:
```bash
pyinstaller --onefile --windowed --name "BLK-BLEDOB Controller" app.py
```

The compiled executable will be available at: `dist/BLK-BLEDOB Controller.exe`

## Technical Specifications 🔌

### Supported BLE Services

```python
SERVICE_UUIDS = [
    "ffd0",
    "fff0", 
    "0000ffd0-0000-1000-8000-00805f9b34fb",
    "0000fff0-0000-1000-8000-00805f9b34fb"
]
```

### Command Protocol

| Function | Command Hex Format |
|----------|-------------------|
| Power ON | `7e0704ff00010201ef` |
| Power OFF | `7e07040000000201ef` |
| Set Color | `7e070503[RR][GG][BB]10ef` |
| Set Brightness | `7e0401[LEVEL]01ff0201ef` |

## Source 📚
Many details have been taken from: [GitHub - dave-code-ruiz/elkbledom](https://github.com/dave-code-ruiz/elkbledom)

