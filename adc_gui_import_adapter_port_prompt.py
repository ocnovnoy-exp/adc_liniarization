
"""
adc_gui_import_adapter.py

Адаптер между GUI и ТВОЕЙ программой.

Главная идея:
    1. GUI импортирует файл с твоей реализацией через importlib.
    2. Основные функции берутся из твоего файла:
       load_ini, open_scpi_resource, set_segment, trigger_single, wait_opc,
       taking_fdat, reduce_fdat, correction, build_correction_array,
       send_correction_array, setup_before_measure_t/r, device_setup.
    3. Всё, что нужно только для GUI, оставлено здесь:
       callbacks, сохранение CSV, безопасное чтение ini, мягкая очистка SYST:ERR?,
       обновление графика по точкам, выбор портов, запрос смены физического порта.

Важно:
    Исходный файл должен быть импортируемым: нижний запуск измерений должен быть под
        if __name__ == "__main__":
    Если использовать файл adc_corrector_ini_importable.py из архива, это уже сделано.
"""

from __future__ import annotations

import csv
import importlib.util
import re
import time
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import pyvisa

VISA_TIMEOUT_MS = 120_000


@dataclass
class DeviceInfo:
    model: str = ""
    version: str = ""
    serial: str = ""
    frequency: str = ""
    port: str = ""
    idn: str = ""
    ready: bool = False


@dataclass
class ScanPoint:
    trace: str
    index: int
    total: int
    source_power_dbm: float
    input_level_db: float
    correction_db: float
    etalon_db: float
    measured_db: float


def parse_idn(idn: str) -> DeviceInfo:
    """Разбирает *IDN?: PLANAR, SN9000-6, 00000001, 25.2.2/2."""
    parts = [p.strip() for p in str(idn).split(",")]
    while len(parts) < 4:
        parts.append("")
    return DeviceInfo(model=parts[1], version=parts[2], serial=parts[3], idn=idn, ready=True)


def is_sn9000_model(model: str) -> bool:
    """SN9000-6 и SN9000-10 считаем корректируемым device."""
    m = model.upper().replace(" ", "")
    return m.startswith("SN9000") or m.startswith("SN-9000")


def port_from_address(address: str) -> str:
    parts = address.split("::")
    return parts[-2] if len(parts) >= 2 else ""


def get_int_from_ini(cfg: ConfigParser, section: str, option: str, fallback: int = 0) -> int:
    """Устойчиво читает int из ini: '0M' -> 0, '100 Hz' -> 100."""
    raw = cfg.get(section, option, fallback=str(fallback))
    match = re.search(r"[-+]?\d+", str(raw))
    if not match:
        return fallback
    return int(match.group(0))


def load_ini_safe(path: str) -> dict:
    """
    Безопасная загрузка ini для GUI.
    По смыслу повторяет твою load_ini(), но не падает, если в поле случайно попала буква.
    """
    cfg = ConfigParser()
    cfg.optionxform = str
    cfg.read(path, encoding="utf-8")

    zones = []
    for i in range(1, 4):
        sec = f"AverageSettingsSection{i}"
        zones.append({
            "bandwidth": get_int_from_ini(cfg, sec, "AverageBand", fallback=1),
            "begin": get_int_from_ini(cfg, sec, "AverageBeginPoint", fallback=0),
            "end": get_int_from_ini(cfg, sec, "AverageEndPoint", fallback=0),
            "avg": get_int_from_ini(cfg, sec, "AverageCount", fallback=1),
        })

    receivers = {}
    if cfg.has_section("ReceiverSettings"):
        for key, value in cfg.items("ReceiverSettings"):
            if key.startswith("Receiver"):
                receivers[key[8:]] = get_int_from_ini(cfg, "ReceiverSettings", key, fallback=0)

    return {
        "frequency": cfg.getfloat("Settings", "Frequency"),
        "device_frequency": cfg.getfloat("Settings", "DeviceFrequency", fallback=cfg.getfloat("Settings", "Frequency")),
        "power_up": cfg.getfloat("Settings", "PowerUpLimit"),
        "power_down": cfg.getfloat("Settings", "PowerDownLimit"),
        "limits": cfg.getfloat("Settings", "Limits", fallback=0.5),
        "zones": zones,
        "receivers": receivers,
    }


def read_ports_from_ini(path: str) -> list[str]:
    """Возвращает список включённых T/R портов из ReceiverSettings."""
    cfg = ConfigParser()
    cfg.optionxform = str
    cfg.read(path, encoding="utf-8")
    ports = []
    if not cfg.has_section("ReceiverSettings"):
        return ports
    for key, value in cfg.items("ReceiverSettings"):
        if not key.startswith("Receiver"):
            continue
        if get_int_from_ini(cfg, "ReceiverSettings", key, fallback=0) == 1:
            ports.append(key[8:])
    # Чтобы порядок был T1,R1,T2,R2...
    def order(name: str):
        return (int(name[1:]), 0 if name[0].upper() == "T" else 1)
    return sorted(ports, key=order)




def physical_port_from_trace(trace: str) -> str:
    """
    Возвращает физический номер порта из имени трассы.

    Примеры:
        T1 -> 1
        R1 -> 1
        T12 -> 12

    Это нужно, чтобы спрашивать пользователя о переключении кабеля
    только при переходе на другой физический порт, а не между T1 и R1.
    """
    match = re.search(r"\d+", str(trace))
    return match.group(0) if match else str(trace)


def import_user_program(path: str):
    """
    Импортирует твою программу обычным importlib.

    Требование: в твоём файле нижний запуск должен быть защищён:
        if __name__ == "__main__":
            main_cli()

    В архиве есть adc_corrector_ini_importable.py — это твой файл с такой защитой.
    """
    path = str(Path(path).resolve())
    module_name = "adc_user_program_imported"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Не удалось импортировать файл: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ImportCoreSession:
    """
    Сессия измерения, которая использует функции из импортированной пользовательской программы.
    """
    def __init__(
        self,
        user_core_path: str,
        log_callback: Optional[Callable[[str], None]] = None,
        point_callback: Optional[Callable[[ScanPoint], None]] = None,
        stop_requested: Optional[Callable[[], bool]] = None,
        port_change_callback: Optional[Callable[[str, str], bool]] = None,
    ):
        self.user_core_path = user_core_path
        self.log_callback = log_callback or print
        self.point_callback = point_callback or (lambda p: None)
        self.stop_requested = stop_requested or (lambda: False)
        # Callback нужен только для GUI: перед началом нового физического порта
        # адаптер просит GUI показать окно "переключите порт" и ждёт OK.
        # Если callback не передан, работа идёт без ожидания пользователя.
        self.port_change_callback = port_change_callback
        self.m = import_user_program(user_core_path)
        self.device = None
        self.generator = None
        self.ini_config = None
        self._patch_runtime_only()

    def log(self, text: str):
        self.log_callback(str(text))

    def _patch_runtime_only(self):
        """
        Небольшие runtime-патчи без изменения твоего файла на диске.
        Они нужны только для GUI и стабильности socket-соединения.
        """
        m = self.m

        # В старых версиях была опечатка querry. Если она осталась, исправляем в памяти.
        def fixed_name_of_instrument(instrument):
            return instrument.query("*IDN?")
        m.name_of_instrument = fixed_name_of_instrument

        # Таймаут 5 сек часто мал для *OPC? на 125 точках/узкой IFBW.
        def open_scpi_resource_long_timeout(address: str):
            inst = m.rm.open_resource(address)
            inst.timeout = VISA_TIMEOUT_MS
            inst.write_termination = "\n"
            inst.read_termination = "\n"
            return inst
        m.open_scpi_resource = open_scpi_resource_long_timeout

        # SERV:REC:... ? на SN9000-6 может давать timeout/-110, поэтому для GUI
        # оставляем управляющие команды, но убираем обязательное чтение состояния.
        def safe_device_switching_setup():
            m.device.write("SENS:ROSC:SOUR EXT")
            m.device.write("OUTP:STATE 1")
            m.device.write("TRIGGER:SOURCE BUS")
            m.device.write("INIT:CONT 1")
            m.device.write("TRIGGER:WAIT WAIT")
            m.device.write("SERV:REC:CORR:STATE 0")
            time.sleep(0.05)
            m.device.write("SERV:REC:LIN:STATE 0")
            time.sleep(0.05)
        m.device_switching_setup = safe_device_switching_setup

        # Строгий syst_err в GUI заменяем на мягкое чтение/очистку.
        def soft_syst_err(instrument):
            try:
                ans = instrument.query("SYST:ERR?").strip()
                if ans != '0,"No error"':
                    self.log(f"WARNING SYST:ERR?: {ans}")
                return ans
            except Exception as exc:
                self.log(f"WARNING cannot read SYST:ERR?: {exc}")
                return "unknown"
        m.syst_err = soft_syst_err

        # FDAT читаем с фильтрацией пустых элементов.
        def safe_taking_fdat(instrument):
            instrument.write("CALC:PARAMETER1:SELECT")
            raw = instrument.query("CALC:DATA:FDAT?").strip()
            return [float(x.strip()) for x in raw.split(",") if x.strip()]
        m.taking_fdat = safe_taking_fdat

    def close(self):
        for inst in (self.device, self.generator):
            try:
                if inst is not None:
                    inst.close()
            except Exception:
                pass
        self.device = None
        self.generator = None

    def configure_from_ini(self, ini_path: str):
        """Читает ini и выставляет глобальные переменные, которые ожидает твоя программа."""
        m = self.m
        # Сначала пробуем твою функцию. Если ini испорчен вроде 0M — используем безопасную.
        try:
            cfg = m.load_ini(ini_path)
        except Exception as exc:
            self.log(f"WARNING: user load_ini failed: {exc}; using load_ini_safe")
            cfg = load_ini_safe(ini_path)
        self.ini_config = cfg

        m.ini_config = cfg
        m.NUMBER_OF_POINTS = cfg["zones"][-1]["end"] - cfg["zones"][0]["begin"] + 1
        m.MAX_POWER = cfg["power_up"]
        m.MIN_POWER = cfg["power_down"]
        m.ENUMERATION_OF_PORTS = cfg["receivers"]
        m.FREQUENCY = cfg["frequency"]
        m.ZONES_FROM_INI = cfg["zones"]
        self.log(f"INI loaded: {ini_path}")
        self.log(f"Frequency={m.FREQUENCY}, points={m.NUMBER_OF_POINTS}")

    def connect(self, ip: str = "127.0.0.1", generator_port: int = 5025, device_port: int = 5026):
        """Открывает оба socket-адреса и определяет device/generator по *IDN?."""
        self.close()
        m = self.m
        addresses = [
            f"TCPIP0::{ip}::{generator_port}::SOCKET",
            f"TCPIP0::{ip}::{device_port}::SOCKET",
        ]
        opened = []
        for addr in addresses:
            inst = m.open_scpi_resource(addr)
            idn = inst.query("*IDN?").strip()
            info = parse_idn(idn)
            info.port = port_from_address(addr)
            self.log(f"{addr} -> {idn}")
            opened.append((addr, inst, info))

        adc = None
        gen = None
        for addr, inst, info in opened:
            if is_sn9000_model(info.model):
                adc = (addr, inst, info)
            else:
                gen = (addr, inst, info)

        if adc is None or gen is None:
            for _, inst, _ in opened:
                try: inst.close()
                except Exception: pass
            raise RuntimeError(f"Не удалось определить device/generator. IDN={[x[2].idn for x in opened]}")

        self.device = adc[1]
        self.generator = gen[1]
        m.device = self.device
        m.generator = self.generator
        m.DEVICE_ADDRESS = adc[0]
        m.GENERATOR_ADDRESS = gen[0]

        gen_info = gen[2]
        dev_info = adc[2]
        if self.ini_config:
            gen_info.frequency = str(self.ini_config.get("frequency", ""))
            dev_info.frequency = str(self.ini_config.get("device_frequency", self.ini_config.get("frequency", "")))
        return gen_info, dev_info

    def _set_segment_both_for_work_ifbw(self, active, passive, bandwidth: int):
        """
        Дополнительная GUI-правка для T-портов:
        рабочую IFBW задаём и активному источнику, и пассивному измерителю.
        Твоя функция set_segment используется без изменения.
        """
        self.m.set_segment(active, self.m.FREQUENCY, bandwidth)
        self.m.set_segment(passive, self.m.FREQUENCY, bandwidth)

    def _measure_point_for_gui(self, trace: str, power_grid: list[float], n: int) -> tuple[float, float]:
        """
        Измеряет одну точку, используя функции из твоего файла.

        Отличие от прямого вызова measure_point_t/r:
            - мы можем передать точку в GUI;
            - задаём рабочую IFBW на оба прибора, что важно для T;
            - не меняем исходный файл.
        """
        m = self.m
        bandwidth = m.get_bandwidth_for_zone(n)

        if trace[0].upper() == "T":
            active = m.generator
            passive = m.device
        else:
            active = m.device
            passive = m.generator

        # Твоя функция: задаёт SOURce1:POWer, быстрый IFBW=1000, рабочий segment активному источнику.
        m.setting_scan_type(active, power_grid, n)

        # Дополнение для GUI/стабильности: рабочий segment пассивному прибору тоже.
        self._set_segment_both_for_work_ifbw(active, passive, bandwidth)

        m.trigger_single(active)
        m.trigger_single(passive)
        m.wait_opc(active)
        m.wait_opc(passive)

        gen_val = m.taking_fdat(m.generator)
        dev_val = m.taking_fdat(m.device)
        etalon = m.reduce_fdat(gen_val)
        measured = m.reduce_fdat(dev_val)
        return etalon, measured

    def request_physical_port_change(self, port_number: str, trace: str) -> bool:
        """
        Просит пользователя переключить физический порт.

        Важно: T1 и R1 относятся к одному физическому порту 1, поэтому
        в run_calibration_ports эта функция вызывается только при изменении
        номера порта: 1 -> 2 -> 3 ...

        Возвращает True, если можно продолжать измерение.
        Возвращает False, если пользователь нажал Cancel/Stop.
        """
        message = f"Подключите физический порт {port_number} для измерения {trace}."
        self.log(message)

        if self.port_change_callback is None:
            # Для консольного/тестового запуска без GUI просто пишем сообщение в лог
            # и продолжаем работу. При желании здесь можно заменить на input().
            return True

        return bool(self.port_change_callback(str(port_number), str(trace)))


    def run_calibration_ports(self, traces: list[str], dry_run: bool = True, output_dir: str = "results"):
        """Запускает основной режим для выбранных портов."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        m = self.m
        current_physical_port = None

        for trace in traces:
            if self.stop_requested():
                break

            physical_port = physical_port_from_trace(trace)
            if physical_port != current_physical_port:
                if not self.request_physical_port_change(physical_port, trace):
                    self.log("Measurement cancelled while waiting for port change")
                    return
                current_physical_port = physical_port

            self.log(f"=== Start calibration {trace} ===")
            if trace[0].upper() == "T":
                m.setup_before_measure_t(trace)
            else:
                m.setup_before_measure_r(trace)
            m.device_setup()

            power_grid = m.grid_of_powers()
            etalon_values = []
            measured_values = []
            correction_values = []
            rows = []

            for n, power in enumerate(power_grid):
                if self.stop_requested():
                    self.log("Stop requested")
                    return
                etalon, measured = self._measure_point_for_gui(trace, power_grid, n)
                etalon_values.append(etalon)
                measured_values.append(measured)
                corr = m.correction(n, etalon_values, measured_values)
                correction_values.append(corr)

                point = ScanPoint(
                    trace=trace,
                    index=n + 1,
                    total=len(power_grid),
                    source_power_dbm=power,
                    input_level_db=measured,
                    correction_db=corr,
                    etalon_db=etalon,
                    measured_db=measured,
                )
                self.point_callback(point)
                rows.append([n, power, measured, etalon, measured, corr, m.db_to_linear(measured), m.db_to_linear(corr)])
                self.log(f"{trace} [{n:03d}] P={power:.6f}, input={measured:.6f}, corr={corr:.6f}")

            correction_array = m.build_correction_array(measured_values, correction_values)
            self._save_csv(out / f"calibration_{trace}.csv", rows)
            m.send_correction_array(m.device, trace, correction_array, dry_run=dry_run)
            self.log(f"=== Done {trace} ===")

        self.log("Calibration finished")

    @staticmethod
    def _save_csv(path: Path, rows: list[list]):
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["index", "source_power_dbm", "input_level_db", "etalon_db", "measured_db", "correction_db", "linear_input", "linear_correction"])
            writer.writerows(rows)
