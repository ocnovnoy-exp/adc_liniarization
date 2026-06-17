
"""
adc_corrector_gui_import_no_main_ports.py

GUI для основного режима, который ИМПОРТИРУЕТ твою программу и вызывает её функции.

Файлы рядом:
    adc_corrector_ini.py                 — основная программа
    adc_corrector_adapter_for_gui.py     — адаптер между GUI и основной программой
    adc_corrector_gui.py                 — этот GUI

Основная программа подключается автоматически через адаптер.
Пункт выбора отдельного Python-файла из меню удалён.
"""

from __future__ import annotations

import re
import sys
import traceback
import threading
from configparser import ConfigParser
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QProgressBar, QPlainTextEdit, QVBoxLayout,
    QWidget, QSpinBox, QGridLayout
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.ticker import MultipleLocator

from adc_corrector_adapter_for_gui import ImportCoreSession, ScanPoint, read_ports_from_ini, load_ini_safe

PORT_COUNT = 16



def resource_path(filename: str) -> Path:
    """
    Возвращает путь к ресурсу при запуске из Python и из PyInstaller EXE.
    В режиме --onefile встроенные файлы распаковываются в sys._MEIPASS.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / filename
    return Path(__file__).resolve().parent / filename


def application_dir() -> Path:
    """
    Папка приложения.

    В режиме PyInstaller --onefile ``__file__`` указывает во временную папку
    ``_MEIPASS``. Для пользовательских результатов нужна папка самого EXE,
    поэтому используем ``sys.executable``.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = application_dir()


def clean_int_text(text: str, fallback: int = 0) -> str:
    m = re.search(r"[-+]?\d+", str(text))
    return str(int(m.group(0))) if m else str(fallback)


class CommonSettingsDialog(QDialog):
    """Окно Settings -> Common settings: IP и socket-порты."""
    def __init__(self, ip: str, gen_port: int, dev_port: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Common settings")
        self.ip_edit = QLineEdit(ip)
        self.gen_port = QSpinBox(); self.gen_port.setRange(1, 65535); self.gen_port.setValue(gen_port)
        self.dev_port = QSpinBox(); self.dev_port.setRange(1, 65535); self.dev_port.setValue(dev_port)
        form = QFormLayout()
        form.addRow("IP Address", self.ip_edit)
        form.addRow("Generator socket port", self.gen_port)
        form.addRow("Device socket port", self.dev_port)
        save = QPushButton("Save"); cancel = QPushButton("Exit")
        save.clicked.connect(self.accept); cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout(); buttons.addWidget(save); buttons.addWidget(cancel)
        layout = QVBoxLayout(self); layout.addLayout(form); layout.addLayout(buttons)

    def values(self):
        return self.ip_edit.text().strip(), int(self.gen_port.value()), int(self.dev_port.value())


class DeviceSettingsDialog(QDialog):
    """Окно Settings -> Device setting: зоны IFBW, частоты, мощности, выбор T/R портов."""
    def __init__(self, ini_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Device settings")
        self.resize(760, 520)
        self.ini_path = ini_path
        self.cfg = ConfigParser(); self.cfg.optionxform = str; self.cfg.read(ini_path, encoding="utf-8")
        main = QVBoxLayout(self)

        zones_layout = QHBoxLayout(); self.zone_edits = []
        for idx in range(1, 4):
            sec = f"AverageSettingsSection{idx}"
            box = QGroupBox(f"Range {idx}")
            form = QFormLayout(box)
            begin = QLineEdit(self.cfg.get(sec, "AverageBeginPoint", fallback="0"))
            end = QLineEdit(self.cfg.get(sec, "AverageEndPoint", fallback="0"))
            band = QLineEdit(self.cfg.get(sec, "AverageBand", fallback="1"))
            form.addRow("Begin", begin)
            form.addRow("End", end)
            form.addRow("Bandwidth", band)

            # AverageCount остаётся в ini для совместимости с основной программой,
            # но больше не показывается и не редактируется в Device settings.
            self.zone_edits.append((sec, begin, end, band))
            zones_layout.addWidget(box)
        main.addLayout(zones_layout)

        settings_box = QGroupBox("Device settings")
        settings_layout = QHBoxLayout(settings_box)
        form = QFormLayout()
        self.freq = QLineEdit(self.cfg.get("Settings", "Frequency", fallback="936000000"))
        self.dev_freq = QLineEdit(self.cfg.get("Settings", "DeviceFrequency", fallback=self.freq.text()))
        self.max_power = QLineEdit(self.cfg.get("Settings", "PowerUpLimit", fallback="10"))
        self.min_power = QLineEdit(self.cfg.get("Settings", "PowerDownLimit", fallback="-45"))
        self.limit = QLineEdit(self.cfg.get("Settings", "Limits", fallback="0.5"))
        form.addRow("Gener. freq.", self.freq); form.addRow("Device freq.", self.dev_freq)
        form.addRow("Max power", self.max_power); form.addRow("Min power", self.min_power)
        form.addRow("Limit (dBm)", self.limit)
        settings_layout.addLayout(form)

        self.port_checks = {}

        # Порты в окне Device settings теперь сделаны не вертикальным списком,
        # а горизонтальной таблицей до 16 физических портов.
        # Верхняя строка — номера портов, ниже строки T и R.
        ports_box = QGroupBox("Receiver ports")
        ports_grid = QGridLayout(ports_box)
        ports_grid.addWidget(QLabel("Port"), 0, 0)
        for i in range(1, PORT_COUNT + 1):
            ports_grid.addWidget(QLabel(str(i)), 0, i, alignment=Qt.AlignCenter)

        for row, prefix in enumerate(("T", "R"), start=1):
            ports_grid.addWidget(QLabel(prefix), row, 0)
            for i in range(1, PORT_COUNT + 1):
                name = f"{prefix}{i}"
                key = f"Receiver{name}"
                enabled = self.cfg.getint("ReceiverSettings", key, fallback=0) if self.cfg.has_section("ReceiverSettings") else 0
                cb = QCheckBox()
                cb.setToolTip(name)
                cb.setChecked(bool(enabled))
                self.port_checks[name] = cb
                ports_grid.addWidget(cb, row, i, alignment=Qt.AlignCenter)

        settings_layout.addWidget(ports_box, 1)
        main.addWidget(settings_box)

        save = QPushButton("Save"); cancel = QPushButton("Exit")
        save.clicked.connect(self.save_and_accept); cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout(); buttons.addStretch(1); buttons.addWidget(save); buttons.addWidget(cancel)
        main.addLayout(buttons)

    def save_and_accept(self):
        if not self.cfg.has_section("Settings"):
            self.cfg.add_section("Settings")
        if not self.cfg.has_section("ReceiverSettings"):
            self.cfg.add_section("ReceiverSettings")
        self.cfg.set("Settings", "Frequency", self.freq.text().strip())
        self.cfg.set("Settings", "DeviceFrequency", self.dev_freq.text().strip())
        self.cfg.set("Settings", "PowerUpLimit", self.max_power.text().strip())
        self.cfg.set("Settings", "PowerDownLimit", self.min_power.text().strip())
        self.cfg.set("Settings", "Limits", self.limit.text().strip())
        for sec, begin, end, band in self.zone_edits:
            if not self.cfg.has_section(sec):
                self.cfg.add_section(sec)
            self.cfg.set(sec, "AverageBeginPoint", clean_int_text(begin.text(), 0))
            self.cfg.set(sec, "AverageEndPoint", clean_int_text(end.text(), 0))
            self.cfg.set(sec, "AverageBand", clean_int_text(band.text(), 1))

            # Поле Averaging удалено из интерфейса.
            # Если AverageCount уже есть в ini, оставляем его без изменений.
            # Если его нет, создаём безопасное значение по умолчанию.
            if not self.cfg.has_option(sec, "AverageCount"):
                self.cfg.set(sec, "AverageCount", "1")
        for name, cb in self.port_checks.items():
            self.cfg.set("ReceiverSettings", f"Receiver{name}", "1" if cb.isChecked() else "0")
        with open(self.ini_path, "w", encoding="utf-8") as f:
            self.cfg.write(f)
        self.accept()


class CalibrationWorker(QObject):
    """Рабочий объект в отдельном потоке. Измерение не блокирует GUI."""
    log = Signal(str)
    point = Signal(object)
    error = Signal(str)
    finished = Signal()

    # Сигнал из рабочего потока в GUI-поток:
    # перед началом нового физического порта нужно показать пользователю окно
    # "переключите порт". Сам QMessageBox нельзя показывать из worker-потока.
    port_change = Signal(str, str)  # physical_port, trace

    def __init__(
        self,
        core_path: str,
        ini_path: str,
        traces: list[str],
        ip: str,
        gen_port: int,
        dev_port: int,
        dry_run: bool,
        ask_port_change: bool = True,
    ):
        super().__init__()
        self.core_path = core_path
        self.ini_path = ini_path
        self.traces = traces
        self.ip = ip
        self.gen_port = gen_port
        self.dev_port = dev_port
        self.dry_run = dry_run
        self.ask_port_change = ask_port_change
        self._stop = False
        self._port_event = None
        self._port_result = False

    def stop(self):
        self._stop = True
        # Если пользователь нажал Stop, пока висит окно смены порта,
        # разблокируем worker, чтобы он завершился.
        if self._port_event is not None:
            self._port_result = False
            self._port_event.set()

    def continue_after_port_change(self, accepted: bool):
        """Вызывается GUI-потоком после OK/Cancel в окне смены порта."""
        self._port_result = bool(accepted)
        if self._port_event is not None:
            self._port_event.set()

    def request_port_change(self, physical_port: str, trace: str) -> bool:
        """
        Callback для адаптера.
        Worker ждёт, пока GUI покажет QMessageBox и пользователь нажмёт OK.
        """
        if not self.ask_port_change:
            return True

        self._port_result = False
        self._port_event = threading.Event()
        self.port_change.emit(str(physical_port), str(trace))

        while not self._port_event.wait(0.1):
            if self._stop:
                return False

        return self._port_result

    def run(self):
        session = None
        try:
            session = ImportCoreSession(
                self.core_path,
                self.log.emit,
                self.point.emit,
                lambda: self._stop,
                self.request_port_change,
            )
            session.configure_from_ini(self.ini_path)
            session.connect(self.ip, self.gen_port, self.dev_port)
            session.run_calibration_ports(
                self.traces,
                dry_run=self.dry_run,
                output_dir=str(APP_DIR / "results"),
            )
        except Exception:
            self.error.emit(traceback.format_exc())
        finally:
            if session is not None:
                session.close()
            self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ADC Nonlinearity Corrector")
        self.resize(1300, 760)
        self.ip = "127.0.0.1"; self.gen_port = 5025; self.dev_port = 5026
        self.ini_path = ""
        self.core_path = "__bundled__"  # основная программа подключается автоматически
        self.worker_thread = None; self.worker = None
        self.trace_lines = {}
        self.trace_data = {}
        self._build_ui()

    def _build_ui(self):
        file_menu = self.menuBar().addMenu("File")
        open_ini = file_menu.addAction("Open ini...")
        open_ini.triggered.connect(self.open_ini)

        settings = self.menuBar().addMenu("Settings")
        common = settings.addAction("Common settings")
        common.triggered.connect(self.open_common_settings)
        device = settings.addAction("Device setting")
        device.triggered.connect(self.open_device_settings)

        # Пункты Open user program... и Help удалены.
        # Основная программа подключается автоматически через адаптер.

        root = QWidget(); self.setCentralWidget(root); main = QHBoxLayout(root)
        left = QVBoxLayout(); main.addLayout(left, 0)

        self.gen_fields = self._device_box("Generator", left)
        self.dev_fields = self._device_box("Device", left)
        self.ini_label = QLabel("INI: не выбран"); self.ini_label.setStyleSheet("color: purple;"); left.addWidget(self.ini_label)
        open_ini_btn = QPushButton("Open ini"); open_ini_btn.clicked.connect(self.open_ini); left.addWidget(open_ini_btn)

        # Выбор портов на главной странице убран.
        # Теперь порты выбираются только в Settings -> Device setting,
        # а при запуске GUI читает включённые ReceiverT/ReceiverR из ini.

        # Continued device searching удалён из интерфейса.

        # Dry run убран из интерфейса и выключен: теперь запуск выполняет реальную
        # запись коэффициентов в SERV:RECn:LIN:DATA.
        # Запрос смены физического порта также убран из интерфейса и всегда включён.

        buttons = QHBoxLayout()
        self.search_btn = QPushButton("Search (*IDN?)")
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.search_btn.clicked.connect(self.search_devices); self.start_btn.clicked.connect(self.start_calibration); self.stop_btn.clicked.connect(self.stop_worker)
        buttons.addWidget(self.search_btn); buttons.addWidget(self.start_btn); buttons.addWidget(self.stop_btn); left.addLayout(buttons)
        self.progress = QProgressBar(); left.addWidget(self.progress)
        left.addStretch(1)

        right = QVBoxLayout(); main.addLayout(right, 1)
        self.figure = Figure(figsize=(8, 5)); self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111); right.addWidget(self.canvas, 1)
        self.log_box = QPlainTextEdit(); self.log_box.setReadOnly(True); self.log_box.setMaximumHeight(120); right.addWidget(self.log_box)
        self._init_plot()

    def _device_box(self, title, parent_layout):
        box = QGroupBox(title); form = QFormLayout(box); fields = {}
        for name in ["Model", "Version", "Serial", "Frequency, Hz", "Port"]:
            edit = QLineEdit(); edit.setReadOnly(True); fields[name] = edit; form.addRow(name, edit)
        parent_layout.addWidget(box); return fields

    def _init_plot(self):
        """
        Настраивает график.

        Пределы оси X берутся из ini:
            [Settings]
            PowerUpLimit
            PowerDownLimit

        Пока ini не выбран, используются значения по умолчанию:
            -45 ... +10 dBm.
        """
        self.ax.clear()

        # Оставляем свободную область справа от осей под список каналов.
        # Легенда будет находиться внутри виджета Matplotlib, но уже вне
        # прямоугольной области самого графика и не будет перекрывать линии.
        self.figure.subplots_adjust(
            left=0.08,
            right=0.82,
            bottom=0.11,
            top=0.96,
        )

        power_up = 10.0
        power_down = -45.0
        limit = 0.5

        if self.ini_path:
            try:
                cfg = load_ini_safe(self.ini_path)
                power_up = float(cfg.get("power_up", power_up))
                power_down = float(cfg.get("power_down", power_down))
                limit = float(cfg.get("limits", limit))
            except Exception as exc:
                # Ошибка чтения ini не должна мешать запуску GUI.
                if hasattr(self, "log_box"):
                    self.append_log(f"WARNING: plot settings from ini were not loaded: {exc}")

        self.ax.set_xlabel("Power, dBm")
        self.ax.set_ylabel("Correction / Deviation, dB")

        self.ax.set_xlim(min(power_down, power_up), max(power_down, power_up))
        self.ax.set_ylim(-limit - 0.05, limit + 0.05)
        self.ax.set_autoscalex_on(False)
        self.ax.set_autoscaley_on(False)

        # Более подробная сетка:
        # основные линии по X через 5 dBm, дополнительные через 1 dBm;
        # основные линии по Y через 0.1 dB, дополнительные через 0.02 dB.
        self.ax.xaxis.set_major_locator(MultipleLocator(5))
        self.ax.xaxis.set_minor_locator(MultipleLocator(1))
        self.ax.yaxis.set_major_locator(MultipleLocator(0.1))
        self.ax.yaxis.set_minor_locator(MultipleLocator(0.02))

        self.ax.grid(True, which="major", linewidth=0.8, alpha=0.55)
        self.ax.grid(True, which="minor", linewidth=0.35, linestyle=":", alpha=0.28)

        self.ax.axhline(0, color="gray", linewidth=0.8)
        self.ax.axhline(limit, color="red", linewidth=1.0, label="HighLimit")
        self.ax.axhline(-limit, color="red", linewidth=1.0, label="LowLimit")

        self._update_legend()
        self.trace_lines.clear()
        self.trace_data.clear()
        self.canvas.draw_idle()

    def _update_legend(self):
        """
        Размещает список каналов справа от области графика.

        Параметры подобраны так, чтобы в один вертикальный столбец
        помещались каналы вплоть до T16/R16. Маленький шрифт применяется
        только к легенде и не уменьшает подписи осей или журнал программы.
        """
        handles, labels = self.ax.get_legend_handles_labels()

        if not handles:
            return

        self.ax.legend(
            handles,
            labels,
            # Легенда располагается справа, за пределами области осей.
            loc="upper left",
            bbox_to_anchor=(1.01, 1.0),
            borderaxespad=0.0,
            # Все элементы выводятся одним вертикальным столбцом.
            ncol=1,
            # Уменьшенный шрифт позволяет разместить большое число каналов.
            fontsize=7,
            frameon=True,
            handlelength=1.8,
            handletextpad=0.4,
            labelspacing=0.15,
            borderpad=0.3,
            columnspacing=0.5,
        )

    def append_log(self, text: str):
        self.log_box.appendPlainText(str(text))

    def open_common_settings(self):
        dlg = CommonSettingsDialog(self.ip, self.gen_port, self.dev_port, self)
        if dlg.exec() == QDialog.Accepted:
            self.ip, self.gen_port, self.dev_port = dlg.values()
            self.append_log(f"Common settings saved: ip={self.ip}, gen={self.gen_port}, dev={self.dev_port}")

    def open_ini(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open ini", "", "INI files (*.ini);;All files (*.*)")
        if path:
            self.ini_path = path
            self.ini_label.setText(Path(path).name)
            self.load_ports()
            self._init_plot()
            self.append_log(f"INI selected: {path}")

    def open_device_settings(self):
        if not self.ini_path:
            QMessageBox.warning(self, "INI", "Сначала выбери ini-файл."); return
        dlg = DeviceSettingsDialog(self.ini_path, self)
        if dlg.exec() == QDialog.Accepted:
            self.append_log("Device settings saved to ini")
            self.load_ports()
            self._init_plot()

    def load_ports(self):
        """
        На главной странице список портов больше не показывается.

        Эта функция теперь только обновляет служебную информацию из ini
        (например, частоту в полях Generator/Device) и пишет в лог,
        какие порты сейчас включены в [ReceiverSettings].

        Изменять выбранные порты нужно через:
            Settings -> Device setting -> Receiver ports
        После нажатия Save в этом окне выбор сохраняется в ini.
        """
        if not self.ini_path:
            return

        try:
            cfg = load_ini_safe(self.ini_path)
            self.gen_fields["Frequency, Hz"].setText(str(cfg.get("frequency", "")))
            self.dev_fields["Frequency, Hz"].setText(str(cfg.get("device_frequency", cfg.get("frequency", ""))))
        except Exception as exc:
            self.append_log(f"WARNING cannot read ini for frequency: {exc}")

        try:
            ports = read_ports_from_ini(self.ini_path)
            self.append_log(
                "Ports from ini: " + (", ".join(ports) if ports else "не выбраны")
            )
        except Exception as exc:
            self.append_log(f"WARNING cannot read selected ports from ini: {exc}")

    def selected_traces(self):
        """
        Возвращает выбранные порты из ini.

        Раньше GUI брал список с главной страницы. Теперь главный список убран,
        поэтому единственный источник истины — секция [ReceiverSettings] ini-файла.
        """
        if not self.ini_path:
            return []
        return read_ports_from_ini(self.ini_path)

    def search_devices(self):
        """
        Кнопка Search открывает оба socket-соединения и отправляет *IDN?
        на адреса генератора и корректируемого устройства.

        Ответы *IDN? разбираются в адаптере и выводятся в поля Model,
        Version, Serial и Port.
        """
        session = None
        try:
            self.append_log(
                f"Search: sending *IDN? to {self.ip}:{self.gen_port} "
                f"and {self.ip}:{self.dev_port}"
            )

            session = ImportCoreSession(self.core_path, self.append_log)
            if self.ini_path:
                session.configure_from_ini(self.ini_path)

            # Внутри connect() выполняется instrument.query("*IDN?")
            # для обоих socket-адресов.
            gen, dev = session.connect(self.ip, self.gen_port, self.dev_port)

            self._fill_device_fields(self.gen_fields, gen)
            self._fill_device_fields(self.dev_fields, dev)
            self.append_log("Search (*IDN?) completed")

        except Exception:
            QMessageBox.critical(self, "Search error", traceback.format_exc())

        finally:
            if session is not None:
                session.close()

    def _fill_device_fields(self, fields, info):
        fields["Model"].setText(info.model); fields["Version"].setText(info.version); fields["Serial"].setText(info.serial)
        fields["Frequency, Hz"].setText(info.frequency); fields["Port"].setText(info.port)

    def start_calibration(self):
        if not self.ini_path:
            QMessageBox.warning(self, "INI", "Выбери ini-файл."); return
        traces = self.selected_traces()
        if not traces:
            QMessageBox.warning(
                self,
                "Ports",
                "В ini не выбран ни один порт. Открой Settings -> Device setting и отметь нужные T/R порты."
            )
            return

        self.append_log("Selected ports loaded from ini: " + ", ".join(traces))

        self._init_plot(); self.progress.setValue(0)
        self.worker_thread = QThread(self)
        self.worker = CalibrationWorker(
            self.core_path,
            self.ini_path,
            traces,
            self.ip,
            self.gen_port,
            self.dev_port,
            False,  # dry_run выключен: коэффициенты будут записываться в прибор
            True,   # запрос смены физического порта всегда включён
        )
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.log.connect(self.append_log)
        self.worker.point.connect(self.on_point)
        self.worker.port_change.connect(self.on_port_change_requested)
        self.worker.error.connect(lambda tb: QMessageBox.critical(self, "Calibration error", tb))
        self.worker.finished.connect(self.worker_thread.quit); self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater); self.worker.finished.connect(lambda: self.progress.setValue(100))
        self.start_btn.setEnabled(False); self.worker.finished.connect(lambda: self.start_btn.setEnabled(True))
        self.worker_thread.start()

    def on_port_change_requested(self, physical_port: str, trace: str):
        """
        Показывает оператору окно с просьбой переключить физический порт.

        Важно: этот метод выполняется в GUI-потоке, поэтому здесь безопасно
        показывать QMessageBox. Worker в это время ждёт ответа через threading.Event.
        """
        text = (
            f"Подключите физический порт {physical_port}.\n\n"
            f"Следующее измерение: {trace}.\n"
            "После переключения нажмите OK."
        )
        answer = QMessageBox.question(
            self,
            "Смена физического порта",
            text,
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Ok,
        )

        accepted = answer == QMessageBox.Ok
        self.append_log(
            f"Port change {'accepted' if accepted else 'cancelled'}: "
            f"physical_port={physical_port}, trace={trace}"
        )

        if self.worker is not None:
            self.worker.continue_after_port_change(accepted)


    def stop_worker(self):
        if self.worker is not None:
            self.worker.stop(); self.append_log("Stop requested")

    def on_point(self, point: ScanPoint):
        # Для графика основного режима используем заданную source power.
        # В массив записи всё равно идёт input_level_db внутри адаптера.
        data = self.trace_data.setdefault(point.trace, ([], []))
        data[0].append(point.source_power_dbm); data[1].append(point.correction_db)
        if point.trace not in self.trace_lines:
            (line,) = self.ax.plot(data[0], data[1], label=point.trace)
            self.trace_lines[point.trace] = line
            self._update_legend()
        else:
            line = self.trace_lines[point.trace]; line.set_data(data[0], data[1])
        # Пределы осей задаются в _init_plot() из ini,
        # поэтому autoscale здесь не вызывается.
        self.canvas.draw_idle()
        self.progress.setValue(int(point.index / point.total * 100))


def main():
    app = QApplication(sys.argv)

    # Значок применяется, только если app_icon.ico добавлен в сборку PyInstaller.
    icon_path = resource_path("app_icon.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    win = MainWindow()
    if icon_path.exists():
        win.setWindowIcon(QIcon(str(icon_path)))

    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
