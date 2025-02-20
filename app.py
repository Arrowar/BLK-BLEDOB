import sys
import json
import asyncio
import signal
from pathlib import Path
from PyQt5 import QtWidgets, QtCore, QtGui
from bleak import BleakScanner, BleakClient
import qasync

# BLE Configuration
SERVICE_UUIDS = [
    "ffd0",
    "fff0",
    "0000ffd0-0000-1000-8000-00805f9b34fb",
    "0000fff0-0000-1000-8000-00805f9b34fb"
]
WRITE_UUIDS = [
    "ffd4",
    "fff3",
    "0000ffd4-0000-1000-8000-00805f9b34fb",
    "0000fff3-0000-1000-8000-00805f9b34fb"
]

class SettingsManager:
    """Manages application settings with JSON persistence"""
    def __init__(self):
        self.settings_file = Path("settings.json")
        self.default_settings = {
            "last_color": "#7e57c2",
            "last_brightness": 75,
            "power_state": False,
            "window_geometry": None
        }
        self.settings = self.default_settings.copy()
        
    def load_settings(self):
        """Load settings from JSON file"""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    self.settings.update(json.load(f))
        except Exception as e:
            print(f"Settings error: {e}")
            self.reset_settings()

    def save_settings(self):
        """Save settings to JSON file"""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Settings error: {e}")

    def reset_settings(self):
        """Reset to default settings"""
        self.settings = self.default_settings.copy()

def normalize_uuid(uuid_str: str) -> str:
    """Normalize BLE UUID to 4-character format"""
    return uuid_str.lower().replace("-", "")[4:8]

EXPECTED_WRITE_NORMS = [normalize_uuid(u) for u in WRITE_UUIDS]

def build_command(command_type: str, value) -> bytes:
    """Generate BLE command bytes based on command type"""
    if command_type == 'power':
        return bytes.fromhex('7e0704ff00010201ef' if value else '7e07040000000201ef')
    elif command_type == 'color':
        hex_color = value.lstrip('#')
        r, g, b = (int(hex_color[i:i+2], 16) for i in range(0, 6, 2))
        return bytes([0x7e, 0x07, 0x05, 0x03, r, g, b, 0x10, 0xef])
    elif command_type == 'brightness':
        level = min(max(round(value * 2.55), 0), 255)
        return bytes([0x7E, 0x04, 0x01, level, 0x01, 0xFF, 0x02, 0x01, 0xEF])
    raise ValueError("Invalid command type")

class MainWindow(QtWidgets.QMainWindow):
    """Modern BLE LED Controller Interface"""
    def __init__(self):
        super().__init__()
        self.settings = SettingsManager()
        self.settings.load_settings()
        self.client = None
        self.connected_device = None
        self.write_char = None
        self.ble_devices = []
        self.ble_lock = asyncio.Lock()
        self.init_ui()
        self.load_initial_state()

    def init_ui(self):
        """Initialize modern UI components"""
        self.setWindowTitle("BLK-BLEDOB Control")
        self.setMinimumSize(840, 620)
        
        # Window geometry handling
        if self.settings.settings["window_geometry"]:
            self.restoreGeometry(QtCore.QByteArray.fromHex(
                self.settings.settings["window_geometry"].encode()))

        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)

        # UI Components
        self.scan_button = self.create_button("Scan Devices")
        self.devices_list = QtWidgets.QListWidget()
        self.connect_button = self.create_button("Connect", enabled=False)
        self.disconnect_button = self.create_button("Disconnect", enabled=False)
        self.power_button = self.create_button("Power ON", enabled=False)
        self.color_button = self.create_color_button()
        self.brightness_slider = self.create_slider()
        self.status_label = QtWidgets.QLabel("Status: Disconnected")

        # Layout
        main_layout = QtWidgets.QHBoxLayout()
        left_panel = self.create_left_panel()
        right_panel = self.create_right_panel()
        
        main_layout.addLayout(left_panel, 40)
        main_layout.addLayout(right_panel, 60)
        central_widget.setLayout(main_layout)

        # Signal connections
        self.scan_button.clicked.connect(self.scan_devices)
        self.connect_button.clicked.connect(self.handle_connect)
        self.disconnect_button.clicked.connect(self.handle_disconnect)
        self.power_button.clicked.connect(self.toggle_power)
        self.color_button.clicked.connect(self.choose_color)
        self.brightness_slider.valueChanged.connect(self.change_brightness)

    def create_button(self, text, enabled=True):
        """Create styled buttons with modern look"""
        btn = QtWidgets.QPushButton(text)
        btn.setEnabled(enabled)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: #ffffff;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-size: 14px;
                min-width: 120px;
            }
            QPushButton:enabled:hover {
                background-color: #4a4a4a;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #666666;
            }
        """)
        return btn

    def create_color_button(self):
        """Create color selection button"""
        btn = QtWidgets.QPushButton()
        btn.setFixedSize(100, 100)
        btn.setStyleSheet("""
            QPushButton {
                border-radius: 50px;
                border: 3px solid #ffffff;
                background-color: %s;
            }
            QPushButton:hover {
                border: 3px solid #64b5f6;
            }
        """ % self.settings.settings["last_color"])
        btn.setEnabled(False)
        return btn

    def create_slider(self):
        """Create modern styled slider"""
        slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #393939;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 20px;
                margin: -8px 0;
                border-radius: 10px;
                border: 2px solid #393939;
            }
            QSlider::sub-page:horizontal {
                background: #64b5f6;
                border-radius: 3px;
            }
        """)
        slider.setRange(0, 100)
        slider.setEnabled(False)
        return slider

    def create_left_panel(self):
        """Build left side panel layout"""
        panel = QtWidgets.QVBoxLayout()
        panel.setContentsMargins(10, 10, 10, 10)
        panel.setSpacing(15)
        
        panel.addWidget(self.scan_button)
        panel.addWidget(QtWidgets.QLabel("Available Devices:"))
        panel.addWidget(self.devices_list)
        panel.addWidget(self.connect_button)
        panel.addWidget(self.disconnect_button)
        panel.addWidget(self.status_label)
        
        return panel

    def create_right_panel(self):
        """Build right side control panel"""
        panel = QtWidgets.QVBoxLayout()
        panel.setContentsMargins(20, 30, 20, 20)
        panel.setSpacing(25)
        
        control_box = QtWidgets.QGroupBox("LED Controls")
        control_layout = QtWidgets.QVBoxLayout()
        control_layout.setSpacing(25)
        
        control_layout.addWidget(self.power_button)
        control_layout.addWidget(QtWidgets.QLabel("Color"), 0, QtCore.Qt.AlignCenter)
        control_layout.addWidget(self.color_button, 0, QtCore.Qt.AlignCenter)
        control_layout.addWidget(QtWidgets.QLabel("Brightness"))
        control_layout.addWidget(self.brightness_slider)
        
        control_box.setLayout(control_layout)
        panel.addWidget(control_box)
        
        return panel

    def load_initial_state(self):
        """Initialize UI from saved settings"""
        self.brightness_slider.setValue(self.settings.settings["last_brightness"])
        self.color_button.setStyleSheet(f"""
            background-color: {self.settings.settings['last_color']};
            border-radius: 50px;
            border: 3px solid #ffffff;
        """)
        self.update_power_button()

    def update_power_button(self):
        """Update power button state"""
        state = self.settings.settings["power_state"]
        self.power_button.setText("Power OFF" if state else "Power ON")
        color = "#81c784" if state else "#ef5350"
        self.power_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
            }}
        """)

    def closeEvent(self, event):
        """Handle window close event"""
        self.settings.settings["window_geometry"] = self.saveGeometry().toHex().data().decode()
        self.settings.save_settings()
        super().closeEvent(event)

    async def scan_devices_async(self):
        """Scan for BLE devices"""
        self.status_label.setText("Status: Scanning...")
        self.devices_list.clear()
        try:
            devices = await BleakScanner.discover()
            for dev in devices:
                name = dev.name or "Unknown Device"
                rssi = dev.rssi if hasattr(dev, "rssi") else "N/A"
                item = QtWidgets.QListWidgetItem(f"{name} ({dev.address})")
                item.setData(QtCore.Qt.UserRole, dev)
                self.devices_list.addItem(item)
            self.status_label.setText("Status: Scan completed")
            self.connect_button.setEnabled(True)
        except Exception as e:
            self.status_label.setText("Status: Scan failed")
            print(f"Scan error: {e}")

    def scan_devices(self):
        """Start BLE scan"""
        asyncio.ensure_future(self.scan_devices_async())

    async def setup_characteristics(self):
        """Discover BLE characteristics"""
        self.write_char = None
        for service in self.client.services:
            for char in service.characteristics:
                if normalize_uuid(char.uuid) in EXPECTED_WRITE_NORMS:
                    self.write_char = char.uuid
                    return
        raise Exception("No write characteristic found")

    async def connect_device_async(self, device):
        """Connect to selected device"""
        self.status_label.setText("Status: Connecting...")
        self.client = BleakClient(device.address)
        
        try:
            async with self.ble_lock:
                await self.client.connect()
                self.connected_device = device
                await self.setup_characteristics()
                
            self.status_label.setText(f"Connected: {device.name or device.address}")
            self.enable_controls(True)
            self.settings.settings["power_state"] = True
            self.update_power_button()
            self.settings.save_settings()
            
        except Exception as e:
            self.status_label.setText("Status: Connection failed")
            print(f"Connection error: {e}")
            self.enable_controls(False)

    def handle_connect(self):
        """Handle connect button click"""
        if selected := self.devices_list.selectedItems():
            asyncio.ensure_future(self.connect_device_async(selected[0].data(QtCore.Qt.UserRole)))

    async def disconnect_device_async(self):
        """Disconnect from current device"""
        self.enable_controls(False)
        if self.client and self.client.is_connected:
            async with self.ble_lock:
                await self.client.disconnect()
        self.client = None
        self.connected_device = None
        self.write_char = None
        self.status_label.setText("Status: Disconnected")
        self.settings.settings["power_state"] = False
        self.update_power_button()
        self.settings.save_settings()

    def handle_disconnect(self):
        """Handle disconnect button click"""
        asyncio.ensure_future(self.disconnect_device_async())

    def enable_controls(self, enabled):
        """Enable/disable control elements"""
        self.power_button.setEnabled(enabled)
        self.color_button.setEnabled(enabled)
        self.brightness_slider.setEnabled(enabled)
        self.disconnect_button.setEnabled(enabled)
        self.connect_button.setEnabled(not enabled)

    async def send_command_async(self, command_type, value):
        """Send command to BLE device"""
        if not (self.client and self.client.is_connected and self.write_char):
            return
            
        try:
            command = build_command(command_type, value)
            async with self.ble_lock:
                await self.client.write_gatt_char(self.write_char, command, response=False)
        except Exception as e:
            print(f"Command error: {e}")

    def toggle_power(self):
        """Toggle LED power state"""
        new_state = not self.settings.settings["power_state"]
        self.settings.settings["power_state"] = new_state
        asyncio.ensure_future(self.send_command_async('power', new_state))
        self.update_power_button()
        self.settings.save_settings()

    def choose_color(self):
        """Select and set LED color"""
        color = QtWidgets.QColorDialog.getColor(initial=QtGui.QColor(self.settings.settings["last_color"]))
        if color.isValid():
            hex_color = color.name()
            self.settings.settings["last_color"] = hex_color
            self.color_button.setStyleSheet(f"""
                background-color: {hex_color};
                border-radius: 50px;
                border: 3px solid #ffffff;
            """)
            asyncio.ensure_future(self.send_command_async('color', hex_color))
            self.settings.save_settings()

    def change_brightness(self, value):
        """Adjust LED brightness"""
        self.settings.settings["last_brightness"] = value
        asyncio.ensure_future(self.send_command_async('brightness', value))
        self.settings.save_settings()

def apply_dark_theme(app):
    """Apply modern dark theme"""
    app.setStyle("Fusion")
    dark_palette = QtGui.QPalette()
    dark_palette.setColor(QtGui.QPalette.Window, QtGui.QColor(30, 30, 30))
    dark_palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(240, 240, 240))
    dark_palette.setColor(QtGui.QPalette.Base, QtGui.QColor(18, 18, 18))
    dark_palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(45, 45, 45))
    dark_palette.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(0, 150, 136))
    dark_palette.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(240, 240, 240))
    dark_palette.setColor(QtGui.QPalette.Text, QtGui.QColor(240, 240, 240))
    dark_palette.setColor(QtGui.QPalette.Button, QtGui.QColor(50, 50, 50))
    dark_palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(240, 240, 240))
    dark_palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(100, 149, 237))
    dark_palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(30, 30, 30))
    app.setPalette(dark_palette)
    app.setStyleSheet("""
        QGroupBox {
            color: #64b5f6;
            font-size: 16px;
            border: 1px solid #404040;
            border-radius: 8px;
            margin-top: 20px;
            padding-top: 12px;
        }
        QLabel {
            color: #cccccc;
            font-size: 14px;
        }
        QListWidget {
            background-color: #202020;
            border: 1px solid #404040;
            border-radius: 6px;
        }
    """)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    apply_dark_theme(app)
    
    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, lambda *args: app.quit())
    
    # Set up async event loop
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    window = MainWindow()
    window.show()
    
    with loop:
        loop.run_forever()