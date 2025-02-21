# 20.02.25

import sys
import math
import asyncio
import signal
import qasync

from PyQt5 import QtWidgets, QtCore, QtGui
from bleak import BleakScanner, BleakClient

from Src.const import WRITE_UUIDS, EFFECTS
from Src.settings import SettingsManager, normalize_uuid
from Src.util import build_command


# Variable
EXPECTED_WRITE_NORMS = [normalize_uuid(u) for u in WRITE_UUIDS]


class ColorWheel(QtWidgets.QWidget):
    """Custom color wheel widget"""
    colorChanged = QtCore.pyqtSignal(QtGui.QColor)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 200)
        self.color = QtGui.QColor.fromHsv(0, 255, 255)
        
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        center = QtCore.QPointF(self.width() / 2, self.height() / 2)
        radius = min(self.width(), self.height()) / 2 - 5
        
        points_per_degree = 3
        for i in range(360 * points_per_degree):
            hue = i / points_per_degree
            painter.setPen(QtGui.QPen(QtGui.QColor.fromHsv(int(hue), 255, 255), 2))
            angle = math.radians(hue)
            point = QtCore.QPointF(
                center.x() + radius * math.cos(angle),
                center.y() - radius * math.sin(angle)
            )
            painter.drawPoint(point)
            
        # Draw selected color marker
        painter.setPen(QtGui.QPen(QtCore.Qt.black, 2))
        angle = math.radians(self.color.hue())
        marker_point = QtCore.QPointF(
            center.x() + radius * math.cos(angle),
            center.y() - radius * math.sin(angle)
        )
        painter.drawEllipse(marker_point, 5, 5)

    def mousePressEvent(self, event):
        self.updateColor(event.pos())
        
    def mouseMoveEvent(self, event):
        self.updateColor(event.pos())
        
    def updateColor(self, pos):
        center = QtCore.QPointF(self.width() / 2, self.height() / 2)
        angle = math.atan2(center.y() - pos.y(), pos.x() - center.x())
        hue = math.degrees(angle)
        if hue < 0:
            hue += 360
        
        self.color.setHsv(int(hue), self.color.saturation(), self.color.value())
        self.colorChanged.emit(self.color)
        self.update()


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
        
        # Store slider references
        self.hue_slider = None
        self.sat_slider = None
        self.val_slider = None
        
        self.init_ui()
        self.load_initial_state()
        
        if self.settings.settings["auto_connect"]:
            asyncio.ensure_future(self.auto_connect_device())

    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("BLK-BLEDOB Control")
        self.setMinimumSize(1000, 700)
        
        if self.settings.settings["window_geometry"]:
            self.restoreGeometry(QtCore.QByteArray.fromHex(
                self.settings.settings["window_geometry"].encode()))

        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)

        # Create main layout
        main_layout = QtWidgets.QHBoxLayout()
        left_panel = self.create_left_panel()
        right_panel = self.create_right_panel()
        
        main_layout.addLayout(left_panel, 40)
        main_layout.addLayout(right_panel, 60)
        central_widget.setLayout(main_layout)

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
    
    def create_left_panel(self):
        """Create the left panel with connection controls"""
        panel = QtWidgets.QVBoxLayout()
        panel.setContentsMargins(10, 10, 10, 10)
        panel.setSpacing(15)
        
        # Connection controls
        self.scan_button = self.create_button("Scan Devices")
        self.devices_list = QtWidgets.QListWidget()
        self.connect_button = self.create_button("Connect", enabled=False)
        self.disconnect_button = self.create_button("Disconnect", enabled=False)
        self.auto_connect_checkbox = QtWidgets.QCheckBox("Auto-connect on startup")
        self.auto_connect_checkbox.setChecked(self.settings.settings["auto_connect"])
        self.status_label = QtWidgets.QLabel("Status: Disconnected")
        
        panel.addWidget(self.scan_button)
        panel.addWidget(QtWidgets.QLabel("Available Devices:"))
        panel.addWidget(self.devices_list)
        panel.addWidget(self.connect_button)
        panel.addWidget(self.disconnect_button)
        panel.addWidget(self.auto_connect_checkbox)
        panel.addWidget(self.status_label)
        
        # Connect signals
        self.scan_button.clicked.connect(self.scan_devices)
        self.connect_button.clicked.connect(self.handle_connect)
        self.disconnect_button.clicked.connect(self.handle_disconnect)
        self.auto_connect_checkbox.stateChanged.connect(self.toggle_auto_connect)
        
        return panel

    def create_right_panel(self):
        """Create the right panel with LED controls"""
        panel = QtWidgets.QVBoxLayout()
        panel.setContentsMargins(20, 30, 20, 20)
        panel.setSpacing(25)
        
        # Power control
        self.power_button = self.create_button("Power ON", enabled=False)
        self.power_button.clicked.connect(self.toggle_power)
        panel.addWidget(self.power_button)
        
        # Color controls
        color_box = QtWidgets.QGroupBox("Color Control")
        color_layout = QtWidgets.QVBoxLayout()
        
        self.color_wheel = ColorWheel()
        self.color_wheel.colorChanged.connect(self.on_color_wheel_change)
        self.color_wheel.setEnabled(False)
        
        # HSV sliders - store both container and slider references
        hue_container, self.hue_slider = self.create_hsv_slider("Hue", 0, 359)
        sat_container, self.sat_slider = self.create_hsv_slider("Saturation", 0, 100)
        val_container, self.val_slider = self.create_hsv_slider("Value", 0, 100)
        
        color_layout.addWidget(self.color_wheel, 0, QtCore.Qt.AlignCenter)
        color_layout.addWidget(hue_container)
        color_layout.addWidget(sat_container)
        color_layout.addWidget(val_container)
        color_box.setLayout(color_layout)
        panel.addWidget(color_box)
        
        effect_box = QtWidgets.QGroupBox("Effects")
        effect_layout = QtWidgets.QVBoxLayout()
        
        self.effect_combo = QtWidgets.QComboBox()
        self.effect_combo.addItems(sorted(EFFECTS.keys()))
        self.effect_combo.currentTextChanged.connect(self.change_effect)
        self.effect_combo.setEnabled(False)
        
        self.speed_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.speed_slider.setRange(1, 100)
        self.speed_slider.setValue(self.settings.settings["last_effect_speed"])
        self.speed_slider.valueChanged.connect(self.change_speed)
        self.speed_slider.setEnabled(False)
        
        effect_layout.addWidget(QtWidgets.QLabel("Select Effect:"))
        effect_layout.addWidget(self.effect_combo)
        effect_layout.addWidget(QtWidgets.QLabel("Effect Speed:"))
        effect_layout.addWidget(self.speed_slider)
        effect_box.setLayout(effect_layout)
        panel.addWidget(effect_box)
        
        # Brightness control
        brightness_box = QtWidgets.QGroupBox("Brightness")
        brightness_layout = QtWidgets.QVBoxLayout()
        self.brightness_slider = self.create_slider()
        self.brightness_slider.valueChanged.connect(self.change_brightness)
        self.brightness_slider.setEnabled(False)
        brightness_layout.addWidget(self.brightness_slider)
        brightness_box.setLayout(brightness_layout)
        panel.addWidget(brightness_box)
        
        return panel

    def load_initial_state(self):
        """Load saved settings and initialize UI state"""
        self.brightness_slider.setValue(self.settings.settings["last_brightness"])
        
        if self.settings.settings["last_effect"]:
            index = self.effect_combo.findText(self.settings.settings["last_effect"])
            if index >= 0:
                self.effect_combo.setCurrentIndex(index)
        
        # Set HSV values
        h, s, v = self.settings.settings["last_hsv"]
        self.hue_slider.setValue(h)
        self.sat_slider.setValue(s)
        self.val_slider.setValue(v)
        
        self.update_power_button()

    def enable_controls(self, enabled):
        """Enable or disable all control elements"""
        self.power_button.setEnabled(enabled)
        self.color_wheel.setEnabled(enabled)
        self.hue_slider.setEnabled(enabled)
        self.sat_slider.setEnabled(enabled)
        self.val_slider.setEnabled(enabled)
        self.effect_combo.setEnabled(enabled)
        self.speed_slider.setEnabled(enabled)
        self.brightness_slider.setEnabled(enabled)
        self.disconnect_button.setEnabled(enabled)
        self.connect_button.setEnabled(not enabled)

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
    
    async def auto_connect_device(self):
        """Attempt to auto-connect to last used device"""
        if self.settings.settings["auto_connect"] and self.settings.settings["last_device"]:
            self.status_label.setText("Status: Auto-connecting...")
            devices = await BleakScanner.discover()
            for dev in devices:
                if dev.address == self.settings.settings["last_device"]:
                    await self.connect_device_async(dev)
                    break

    def toggle_auto_connect(self, state):
        """Toggle auto-connect setting"""
        self.settings.settings["auto_connect"] = bool(state)
        self.settings.save_settings()

    async def scan_devices_async(self):
        """Scan for BLE devices"""
        self.status_label.setText("Status: Scanning...")
        self.devices_list.clear()
        try:
            devices = await BleakScanner.discover()
            for dev in devices:
                name = dev.name or "Unknown Device"
                rssi = dev.advertisement_data.rssi if hasattr(dev, "advertisement_data") and hasattr(dev.advertisement_data, "rssi") else "N/A"
                item = QtWidgets.QListWidgetItem(f"{name} ({dev.address}) RSSI: {rssi}")
                item.setData(QtCore.Qt.UserRole, dev)
                self.devices_list.addItem(item)
            self.status_label.setText("Status: Scan completed")
            self.connect_button.setEnabled(True)
        except Exception as e:
            self.status_label.setText("Status: Scan failed")
            print(f"Scan error: {e}")

    def scan_devices(self):
        """Start BLE device scan"""
        asyncio.ensure_future(self.scan_devices_async())

    async def connect_device_async(self, device):
        """Connect to selected BLE device"""
        self.status_label.setText("Status: Connecting...")
        self.client = BleakClient(device.address)
        
        try:
            async with self.ble_lock:
                await self.client.connect()
                self.connected_device = device
                await self.setup_characteristics()
                
            self.status_label.setText(f"Connected: {device.name or device.address}")
            self.settings.settings["last_device"] = device.address
            self.enable_controls(True)
            self.settings.settings["power_state"] = True
            self.update_power_button()
            self.settings.save_settings()
            
        except Exception as e:
            self.status_label.setText("Status: Connection failed")
            print(f"Connection error: {e}")
            self.enable_controls(False)

    async def setup_characteristics(self):
        """Discover BLE characteristics"""
        self.write_char = None
        for service in self.client.services:
            for char in service.characteristics:
                if normalize_uuid(char.uuid) in EXPECTED_WRITE_NORMS:
                    self.write_char = char.uuid
                    return
        raise Exception("No write characteristic found")

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

    def create_hsv_slider(self, label, min_val, max_val):
        """Create HSV slider with label"""
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout()
        lbl = QtWidgets.QLabel(label)
        
        slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        slider.setRange(min_val, max_val)
        slider.valueChanged.connect(self.update_color_from_sliders)
        slider.setEnabled(False)

        layout.addWidget(lbl)
        layout.addWidget(slider)
        container.setLayout(layout)

        return container, slider

    def toggle_power(self):
        """Toggle LED power state"""
        new_state = not self.settings.settings["power_state"]
        self.settings.settings["power_state"] = new_state
        asyncio.ensure_future(self.send_command_async('power', new_state))
        self.update_power_button()
        self.settings.save_settings()

    def update_power_button(self):
        """Update power button appearance"""
        state = self.settings.settings["power_state"]
        self.power_button.setText("Power OFF" if state else "Power ON")
        color = "#81c784" if state else "#ef5350"
        self.power_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-size: 14px;
                min-width: 120px;
            }}
        """)

    def on_color_wheel_change(self, color):
        """Handle color wheel selection"""
        hex_color = color.name()
        asyncio.ensure_future(self.send_command_async('color', hex_color))
        self.settings.settings["last_color"] = hex_color
        self.settings.settings["last_hsv"] = (color.hue(), color.saturation(), color.value())
        self.settings.save_settings()

    def update_color_from_sliders(self):
        """Update color based on HSV slider values"""
        if not all([self.hue_slider, self.sat_slider, self.val_slider]):
            return
            
        h = self.hue_slider.value()
        s = int(self.sat_slider.value() * 2.55)
        v = int(self.val_slider.value() * 2.55)
        
        color = QtGui.QColor.fromHsv(h, s, v)
        self.color_wheel.color = color
        self.color_wheel.update()
        self.on_color_wheel_change(color)

    def change_effect(self, effect):
        """Change LED effect"""
        asyncio.ensure_future(self.send_command_async('effect', effect))
        self.settings.settings["last_effect"] = effect
        self.settings.save_settings()

    def change_speed(self, speed):
        """Change effect speed"""
        asyncio.ensure_future(self.send_command_async('speed', speed))
        self.settings.settings["last_effect_speed"] = speed
        self.settings.save_settings()

    def change_brightness(self, value):
        """Change LED brightness"""
        self.settings.settings["last_brightness"] = value
        asyncio.ensure_future(self.send_command_async('brightness', value))
        self.settings.save_settings()

    def closeEvent(self, event):
        """Handle window close event"""
        self.settings.settings["window_geometry"] = self.saveGeometry().toHex().data().decode()
        self.settings.save_settings()
        super().closeEvent(event)

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