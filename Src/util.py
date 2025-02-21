# 21.02.25

from Src.const import EFFECTS

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
    elif command_type == 'effect':
        effect_id = EFFECTS.get(value, 0x87)
        return bytes([0x7E, 0x07, 0x03, effect_id, 0x03, 0xFF, 0xFF, 0x00, 0xEF])
    elif command_type == 'speed':
        speed_byte = min(max(round(value * 2.55), 0), 255)
        return bytes([0x7E, 0x07, 0x02, speed_byte, 0xFF, 0xFF, 0xFF, 0x00, 0xEF])
    raise ValueError("Invalid command type")