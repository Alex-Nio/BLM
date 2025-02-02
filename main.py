import os
import asyncio
from bleak import BleakClient, BleakError, BleakScanner
import logging
import json

# Конфигурация логирования
logging.basicConfig(level=logging.DEBUG, format='\U0001F4AC %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Файл для хранения переименованных устройств
DEVICE_NAMES_FILE = "device_names.json"

# UUID сервиса и характеристики
SERVICE_UUID = "0000a032-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_UUID = "0000a040-0000-1000-8000-00805f9b34fb"

# Команды управления лампой
COMMANDS = {
    "Light On": [0x55, 0xAA, 0x01, 0x08, 0x05, 0x01],
    "Light Off": [0x55, 0xAA, 0x01, 0x08, 0x05, 0x00],
    "Color Red": [0x55, 0xAA, 0x03, 0x08, 0x02, 0xFF, 0x00, 0x00],
    "Color Green": [0x55, 0xAA, 0x03, 0x08, 0x02, 0x00, 0xFF, 0x00],
    "Color Blue": [0x55, 0xAA, 0x03, 0x08, 0x02, 0x00, 0x00, 0xFF],
    "Color White": [0x55, 0xAA, 0x01, 0x08, 0x09, 0x01],
    "Color Alarm": [0x55, 0xAA, 0x01, 0x08, 0x06, 0x07],
    "Color Rainbow": [0x55, 0xAA, 0x01, 0x08, 0x06, 0x01],
}

def create_packet(command):
    """Создаёт правильный формат пакета с контрольной суммой"""
    checksum = (256 - sum(command[2:]) % 256) & 0xFF
    command.append(checksum)
    return bytearray(command)

def load_device_names():
    """Загружает сохранённые имена устройств."""
    if os.path.exists(DEVICE_NAMES_FILE):
        with open(DEVICE_NAMES_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_device_names(device_names):
    """Сохраняет имена устройств в файл."""
    with open(DEVICE_NAMES_FILE, 'w') as f:
        json.dump(device_names, f)

def get_device_display_name(device):
    """Возвращает запомненное имя устройства, если оно есть."""
    device_names = load_device_names()
    return device_names.get(device.address, device.name or "Без имени")

async def scan_devices():
    """Сканирование Bluetooth-устройств."""
    logger.info("🔎 Начинаем поиск устройств...")
    devices = await BleakScanner.discover()
    if not devices:
        logger.warning("⚠️ Устройства не найдены. Повторите попытку позже.")
    return devices

async def search_new_device():
    """Меню выбора нового устройства."""
    devices = await scan_devices()
    if not devices:
        return

    device_names = load_device_names()
    for i, device in enumerate(devices, 1):
        display_name = get_device_display_name(device)
        print(f"{i}. {display_name} ({device.address})")

    selected = input("Выберите устройство или нажмите Enter для возврата: ")
    if selected.isdigit() and 1 <= int(selected) <= len(devices):
        address = devices[int(selected) - 1].address
        name = input("Введите имя устройства или нажмите Enter для пропуска: ")
        if name:
            device_names[address] = name
            save_device_names(device_names)

            # 🔄 Принудительно обновляем список устройств после переименования
            global MAIN_DEVICE_NAMES
            MAIN_DEVICE_NAMES = load_device_names()
            print(f"✅ Имя устройства сохранено: {name}")

        await connect_to_device(address)

async def edit_device_name():
    """Позволяет редактировать имена запомненных устройств."""
    device_names = load_device_names()
    if not device_names:
        print("⚠️ Нет запомненных устройств для редактирования.")
        return

    print("\n📋 Запомненные устройства:")
    for i, (address, name) in enumerate(device_names.items(), 1):
        print(f"{i}. {name} ({address})")

    selected = input("Выберите устройство для редактирования или нажмите Enter для возврата: ")
    if selected.isdigit() and 1 <= int(selected) <= len(device_names):
        address = list(device_names.keys())[int(selected) - 1]
        new_name = input(f"Введите новое имя для {device_names[address]} ({address}): ")
        if new_name:
            device_names[address] = new_name
            save_device_names(device_names)

            # 🔄 Принудительно обновляем список устройств
            global MAIN_DEVICE_NAMES
            MAIN_DEVICE_NAMES = load_device_names()
            print(f"✅ Имя устройства обновлено: {new_name}")

async def main_menu():
    """Главное меню выбора устройства."""
    global MAIN_DEVICE_NAMES
    while True:
        MAIN_DEVICE_NAMES = load_device_names()  # Принудительно загружаем свежие данные
        device_names = MAIN_DEVICE_NAMES

        print("\n📌 Главное меню:")
        print("1. 📂 Выбор устройства из запомненных")
        print("2. ✏️  Редактировать имена устройств")
        print("3. 🔎 Поиск нового устройства")
        print("4. 🚪 Выход")
        choice = input("Введите номер: ")

        if choice == "1":
            if not device_names:
                print("⚠️ Нет запомненных устройств.")
                continue
            for i, (address, name) in enumerate(device_names.items(), 1):
                print(f"{i}. {name} ({address})")
            selected = input("Выберите устройство или нажмите Enter для возврата: ")
            if selected.isdigit() and 1 <= int(selected) <= len(device_names):
                address = list(device_names.keys())[int(selected) - 1]
                await connect_to_device(address)
        elif choice == "2":
            await edit_device_name()
        elif choice == "3":
            await search_new_device()
        elif choice == "4":
            print("👋 Выход из программы.")
            break
        else:
            print("❌ Неверный ввод.")

async def send_command(client, command_name):
    """Отправляет команду устройству"""
    command = COMMANDS.get(command_name)
    if not command:
        logger.error(f"❌ Команда '{command_name}' не найдена.")
        return
    packet = create_packet(command)
    try:
        await client.write_gatt_char(CHARACTERISTIC_UUID, packet)
        logger.info(f"✅ Команда '{command_name}' отправлена: {list(packet)}")
    except Exception as e:
        logger.error(f"⚠️ Ошибка отправки команды '{command_name}': {e}")

async def connect_to_device(address):
    """Подключается к устройству и повторяет попытки при неудаче."""
    client = BleakClient(address)
    retry_count = 3  # Количество попыток подключения
    for attempt in range(retry_count):
        try:
            logger.info(f"🔗 Подключение к {address} (попытка {attempt+1}/{retry_count})...")
            
            # Добавляем таймаут подключения
            await asyncio.wait_for(client.connect(), timeout=10)

            if client.is_connected:
                logger.info(f"✅ Успешно подключено к {address}")
                await control_device(client)
                return
        except asyncio.TimeoutError:
            logger.warning(f"⏳ Истек таймаут подключения к {address}, пробуем снова...")
        except BleakError as e:
            logger.warning(f"⚠️ Ошибка подключения: {e}")
        
        await asyncio.sleep(2)

    logger.error(f"❌ Не удалось подключиться к {address} после {retry_count} попыток.")

async def control_device(client):
    """Меню управления устройством."""
    while True:
        print("\n🎛️ Управление устройством:")
        for i, cmd in enumerate(COMMANDS.keys(), 1):
            print(f"{i}. {cmd}")
        print("q. 🔙 Выход")
        choice = input("Выберите команду: ")
        if choice.lower() == 'q':
            await client.disconnect()
            break
        try:
            cmd_index = int(choice) - 1
            cmd_name = list(COMMANDS.keys())[cmd_index]
            await send_command(client, cmd_name)
        except (ValueError, IndexError):
            print("❌ Неверный ввод.")

if __name__ == "__main__":
    asyncio.run(main_menu())
