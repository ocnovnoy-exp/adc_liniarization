import pyvisa
from configparser import ConfigParser
import time
import matplotlib.pyplot as plt

DEVICE_ADDRESS = "TCPIP0::localhost::5026::SOCKET"
GENERATOR_ADDRESS = "TCPIP0::localhost::5025::SOCKET"

# NUMBER_OF_POINTS = 125
VISA_TIMEOUT_MS = 5000

rm = pyvisa.ResourceManager() # '@py' необходим для принудительного использования бэкенда не NI-VISA, а pyvisa-py
print(rm.list_resources('TCPIP?*')) #'?*' это фильтр необходимый для обнаружения нашего адреса устройства, так как бех него будут искаться только приборы, чьи имена заканчиваются на ::INSTR, а наше заканчивется на ::SOCKET
# Если мы хотим только ::SOCKET, то испольхзуем вот такой фильтр 'TCPIP?*'

device_generator_addresses = ["", ""] #Список для записи адрессов generator и device
list_of_adc = ["SN9000-10"] #Список для устройств которые являются device, а не generator, и это значит мы должны спрашивать количество их портов

def open_scpi_resource(address: str):
    inst = rm.open_resource(address)
    inst.timeout = VISA_TIMEOUT_MS
    inst.write_termination = "\n" # Отправлять \n после каждой команды
    inst.read_termination = "\n" # Ждать \n в конце ответа
    return inst

# def check_address(address: str):# Функиця которую следует использоавть вместо rm.list_resources('TCPIP?*'), потому что она выдаёт неправильные порты
#     try:
#         instrument = open_scpi_resource(address)
#         name = instrument.query("*IDN?").strip()
#         print(f"{address} --> {name}")
#         instrument.close()
#     except Exception as e:
#         print(f"{address} FAIL --> {e}")
#     finally:
#         if instrument is not None:
#             try:
#                 instrument.close()
#             except Exception:
#                 pass

def device_or_generator_func(address: str):#Эта функция нам нужна только для того что бы определить что за устройство мы подключили, generator или device
    instrument = rm.open_resource(address)
    if instrument.query("*IDN?").split(", ")[1] in list_of_adc:#Тут мы разделяем строку которую нам возвращает *IDN?, и смотрим что это за устройство, есть лиона в списке list_of_adc
        device_generator_addresses[1] = address
        instrument.close()
        return
    device_generator_addresses[0] = address
    instrument.close()
    return 

def load_ini(path: str):# Загружаем значения для корректировки из .ini файла
    cfg = ConfigParser()
    cfg.optionxform = str
    cfg.read(path, encoding="utf-8")

    return {
        "frequency": cfg.getfloat("Settings", "Frequency"),
        "device_frequency": cfg.getfloat("Settings", "DeviceFrequency"),
        "power_up": cfg.getfloat("Settings", "PowerUpLimit"),
        "power_down": cfg.getfloat("Settings", "PowerDownLimit"),
        "zones": [
            {
                "bandwidth": cfg.getint("AverageSettingsSection1", "AverageBand"),
                "begin": cfg.getint("AverageSettingsSection1", "AverageBeginPoint"),
                "end": cfg.getint("AverageSettingsSection1", "AverageEndPoint"),
                "avg": cfg.getint("AverageSettingsSection1", "AverageCount"),
            },
            {
                "bandwidth": cfg.getint("AverageSettingsSection2", "AverageBand"),
                "begin": cfg.getint("AverageSettingsSection2", "AverageBeginPoint"),
                "end": cfg.getint("AverageSettingsSection2", "AverageEndPoint"),
                "avg": cfg.getint("AverageSettingsSection2", "AverageCount"),
            },
            {
                "bandwidth": cfg.getint("AverageSettingsSection3", "AverageBand"),
                "begin": cfg.getint("AverageSettingsSection3", "AverageBeginPoint"),
                "end": cfg.getint("AverageSettingsSection3", "AverageEndPoint"),
                "avg": cfg.getint("AverageSettingsSection3", "AverageCount"),
            },
        ],
        "receivers" : {receiver_tuple[0][8:]: int(receiver_tuple[1]) for receiver_tuple in cfg.items("ReceiverSettings")}# Получаем перечень приемников из .ini файла, получаем пару {'T1': 1, ..., 'R32': 0}
    }

def get_info():#Получение информации от приборов, имя, версию и тд.
    dev_idn, gen_idn = [], []
    dev_idn = device.query("*IDN?").split(", ")
    print(dev_idn)
    quantity_of_ports = device.query(":SERV:PORT:COUN?")
    print(quantity_of_ports)
    print(syst_err(device))
    gen_idn = generator.query("*IDN?").split(", ")
    print(gen_idn)
    print(syst_err(generator))
    device.write("syst:pres")
    device.write("trigger:source BUS")
    device.write("init:cont 1")
    device.write("trigger:wait WAIT")
    device.write("sens:rosc:sour EXT")
    syst_err(generator)
    return dev_idn, gen_idn

def device_setup():# Функция в которой мы задаём сегменты для измерения
    device.write("sens1:aver:stat 0")
    set_segment(device, ini_config["frequency"], ini_config["zones"][0]["bandwidth"])

    generator.write("sens1:aver:stat 0")
    set_segment(generator, ini_config["frequency"], ini_config["zones"][0]["bandwidth"])

    syst_err(device)
    syst_err(generator)


def generator_switching_setup():
    generator.write("syst:pres")
    generator.write("calc:par1:def R2")#В логах мы сначала передаем obzor что он R2, а затем что он T2, можно ли обойтись только тем что говорим, что он T2?
    generator.write("calc:par1:spor 2")# !!!!! надо разобарться что с этой командой, где 1, а где 2 ставится

def device_switching_setup():
    device.write("sens:rosc:sour EXT")
    device.write("outp:state 1")
    device.write("trigger:source BUS")
    device.write("init:cont 1")
    device.write("trigger:wait WAIT")
    device.write("serv:rec:corr:state 0")
    device.query("serv:rec:corr:state?")
    device.write("serv:rec:lin:state 0")# Если запускать программу в режиме проверки, то тут будет не 0, а 1
    device.query("serv:rec:lin:state?")

def setup_for_measurement_t(port: str):# Мы передаём сюда порт(когда меняем с R на T) устройства которого мы проверяем, device_port
    generator_switching_setup()
    device.write("syst:pres")
    device.write(f"calc:par1:def {port}")

    device_spor = 2 if int(port[1:]) == 1 else 1# Вот такие настройки у пчелки, надо попробовать с device_spor = 2 if int(port[1:]) == 1 else 1, при чем попробовать для 4 портов
    device.write(f"calc:par1:spor {device_spor}")

    generator.write("trigger:source BUS")
    generator.write("init:cont 1")
    generator.write("trigger:wait WAIT")
    generator.write("outp:state 1")
    device_switching_setup()

def setup_for_measurement_r(port: str):# Мы передаём сюда порт(когда меняем с T на R) устройства которого мы проверяем, device_port
    generator_switching_setup()
    device.write("syst:pres")
    device.write(f"calc:par1:def {port}")
    generator.write("trigger:source BUS")
    generator.write("init:cont 1")
    generator.write("trigger:wait WAIT")
    device.write(f"calc:par1:spor {port[1:]}")
    generator.write("calc:par1:def T2")
    generator.write("outp:state 0")
    device_switching_setup()

def wait_opc(instrument):
    answer_on_opc = instrument.query("*OPC?").strip()
    if answer_on_opc != "1":
        raise RuntimeError(f"Неожиданный ответ на *OPC?, а именно: {answer_on_opc}")

def trigger_single(instrument):
    instrument.write("trig:sing")

def syst_err(instrument):
    answer_on_opc = instrument.query("syst:err?").strip()
    if answer_on_opc != '0,"No error"':
        raise RuntimeError(f"Неожиданный ответ от syst:err?: {answer_on_opc}")
    return answer_on_opc

def grid_of_powers():#Изменение мощности происходит просто определением дельты, и уже после этого мы идем от наибольшей мозности отнимая значение дельты умноженной на номер шага 
    delta_power = (MAX_POWER - MIN_POWER) / (NUMBER_OF_POINTS - 1)
    return [MAX_POWER - delta_power * i for i in range(NUMBER_OF_POINTS)]

def get_bandwidth_for_zone(num_of_point: int, ini_conf: dict):#Функця определяет какое bandwidth для этой точки(в каком из 3 сегментов находится точка)
    for zones_conf in ini_conf.get("zones"):#функция возвращает настройки для сегмента в котором находится точка
        if zones_conf.get("begin") <= num_of_point <= zones_conf.get("end"):
            # if num_of_point == zones_conf.get("begin"):# В начале каждого сегмента мы должны передавать sens1:aver:stat 0, не уверен что это нужно
            #     device.write("sens1:aver:stat 0") # sens1:aver:stat устанавливает или считывает состояние ВКЛ/ВЫКЛ усреднения измерений по соседним разверткам.
            #     generator.write("sens1:aver:stat 0")
            return zones_conf.get("bandwidth")
    raise ValueError(f"Не найдена зона для точки {num_of_point}")

#SENS:SEGM:DATA 100,10 или 3 зависит от ini файла, там 3 сегмента и для каждого своё значение
def set_segment(instrument, frequency_hz: float, ifbw: int):
    instrument.write("SENS:SWE:TYPE SEGM")
    instrument.write(
        "SENS:SEGM:DATA "
        f"5,0,1,0,0,0,2,"
        f"{frequency_hz:.0f},{frequency_hz:.0f},2,{ifbw},"
        f"{frequency_hz:.0f},{frequency_hz:.0f},2,{ifbw}"
    )

def taking_fdat(instrument):#Эта функция считывает список после CALC:DATA:FDAT?
    instrument.write("calc:parameter1:select")
    raw_values = instrument.query("CALC:DATA:FDAT?").split(",")
    values = [float(i.strip()) for i in raw_values]
    print(instrument, values)
    return values


def reduce_fdat(val: list):
    average_weight = 0
    for i in range(0, len(val), 2):
        average_weight += val[i]
    return average_weight / (len(val) / 2)

def configure_point_for_scan(inst1, powers_grid: list, num_of_point: int, ini_conf: dict):#Функция необходимая для задания мощности и отправки SENS:SEGM:DATA 2 раза, с bandwidth = 1000 и той что мы берем их .ini файла
    power = powers_grid[num_of_point]
    bandwidth = get_bandwidth_for_zone(num_of_point, ini_conf)
    print(f"SOURce1:POWer {power:.6e}       {bandwidth}      {num_of_point}")
    inst1.write(f"SOURce1:POWer {power:.6e}")

    set_segment(inst1, ini_conf["frequency"], 1000)# Быстрый проход только на активном источнике
    trigger_single(inst1)
    wait_opc(inst1)

    set_segment(inst1, ini_conf["frequency"], bandwidth)# Рабочий сегмент надо задать ОБОИМ приборам
    # set_segment(inst2, ini_conf["frequency"], bandwidth)


def measure_point_t(power_grid: list, n: int, ini_config):#функция для измерения T порта
    configure_point_for_scan(generator, device, power_grid, n, ini_config)
    syst_err(device)
    trigger_single(device)
    trigger_single(generator)

    wait_opc(device)
    syst_err(device)
    wait_opc(generator)
    syst_err(generator)

    gen_val = taking_fdat(generator)
    dev_val = taking_fdat(device)

    etalon = reduce_fdat(gen_val)
    measured = reduce_fdat(dev_val)

    return etalon, measured

def measure_point_r(power_grid: list, n: int, ini_config):
    syst_err(device)
    configure_point_for_scan(device, generator, power_grid, n, ini_config)
    trigger_single(device)
    syst_err(generator)
    trigger_single(generator)

    wait_opc(device)
    syst_err(device)
    wait_opc(generator)
    syst_err(generator)

    gen_val = taking_fdat(generator)
    dev_val = taking_fdat(device)

    etalon = reduce_fdat(gen_val)
    measured = reduce_fdat(dev_val)

    return etalon, measured

def compute_correction(etalon_i: float, measured_i: float, etalon_0: float, measured_0: float): #Формула correction из старой программы: corr_i = (etalon_i - measured_i) - (etalon_0 - measured_0)
    return (etalon_i - measured_i) - (etalon_0 - measured_0)

def correction(num_in_grid_of_power: int, etalon_list: list, measured_list: list): #Считаем коэффициенты для коррекции
    if num_in_grid_of_power == 0:
        correction = 0.0
    else:
        correction = compute_correction(
            etalon_i = etalon_list[num_in_grid_of_power],
            measured_i = measured_list[num_in_grid_of_power],
            etalon_0 = etalon_list[0],
            measured_0 = measured_list[0],
        )
    return correction

def graphic_solo(x: list, y: list, x_label: str, y_label: str, ax):# Функция для вывода графика с одной функцией
  ax.plot(x, y, color="blue")
  ax.set_xlabel(x_label)
  ax.set_ylabel(y_label)
  ax.grid(True)

def graphic_duo(x: list, y: list, y1: list, x_label: str, legend1: str, legend2: str, ax):# Функция для вывода графика с двумя функциями
  ax.plot(x, y, color="blue")
  ax.plot(x, y1, color="red")
  ax.set_xlabel(x_label)
  ax.set_xlabel(x_label)
  ax.grid(True)
  ax.legend([legend1, legend2])

# Функция для визуализации данных
def visualize_measurement_result(data_of_pictures: list, num_cols: int):#На вход подаём массив из кортежей с настройками каждого графика, который мы хотим вывести, а так же кол-во столбцов
    if len(data_of_pictures) == 0:
        print("Массив с характеристиками пуст, внутри нет ничего для описания графиков")
        return
    num_rows = 1
    fig, axs = plt.subplots(num_rows, num_cols, figsize=(5 * num_cols, 4 * num_rows))
    for i in range(len(axs)):
        current_num_of_picture = i
        if len(data_of_pictures[i]) == 4 and current_num_of_picture < len(data_of_pictures):
            x, y, x_label, y_label = data_of_pictures[i]
            graphic_solo(x, y, x_label, y_label, axs[i])
        elif len(data_of_pictures[i]) == 6 and current_num_of_picture < len(data_of_pictures):
            x, y, y1, x_label, legend1, legend2 = data_of_pictures[i]
            graphic_duo(x, y, y1, x_label, legend1, legend2, axs[i])
        else:
            fig.delaxes(axs[i])
    plt.tight_layout()  
    plt.show()


def measure_all_points_t(port: str,power_grid: list):# Внутри этой функции мы проходим по всем точкам для T порта и считываем значения для обоих устройств
    measured_val = []
    etalon_val = []
    corr_coef_list = []
    for n in range(len(power_grid)):
        etalon, measured = measure_point_t(power_grid, n, ini_config)
        etalon_val.append(etalon)
        measured_val.append(measured)
        corr = correction(n, etalon_val, measured_val)
        corr_coef_list.append(corr)
        print(
            f"{port} [{n:03d}] "
            f"P={power_grid[n]:.6f}, "
            f"etalon={etalon:.6f}, "
            f"measured={measured:.6f}, "
            f"corr={corr:.6f}"
        )
    return etalon_val, measured_val, corr_coef_list

def measure_all_points_r(port: str, power_grid: list):
    measured_val = []
    etalon_val = []
    corr_coef_list = []
    for n in range(len(power_grid)):
        etalon, measured = measure_point_r(power_grid, n, ini_config)
        etalon_val.append(etalon)
        measured_val.append(measured)
        corr = correction(n, etalon_val, measured_val)
        corr_coef_list.append(corr)
        print(
            f"{port} [{n:03d}] "
            f"P={power_grid[n]:.6f}, "
            f"etalon={etalon:.6f}, "
            f"measured={measured:.6f}, "
            f"corr={corr:.6f}"
        )
    return etalon_val, measured_val, corr_coef_list

#выбор того кому передаём source1:power зависит от того кто является R
def measure_port(port: str):#Эта функция нужна для того что бы пройтись по всем мощностям для T/R и записать значения корректировки в массив
    power_grid = grid_of_powers()

    measured_values = []
    etalon_values = []
    correction_coef_list = []

    if port[0] == "T":
        etalon_values, measured_values, correction_coef_list = measure_all_points_t(port, power_grid)
    elif port[0] == "R":
        etalon_values, measured_values, correction_coef_list = measure_all_points_r(port, power_grid)
    else:
        raise ValueError(f"Неизвестный порт: {port}")

    correction_array = build_correction_array(
        measured_values,
        correction_coef_list
    )

    data_for_vizualization = [# В этот список мы записываем то что хотим визуализировать, ось x, ось y, подпись к оси x и подпись к оси y
    (power_grid, correction_coef_list, "Сетка мощностей", "Коэфициенты корреляции"),
    (power_grid, measured_values, etalon_values,"Сетка мощностей", "fdat c SN9000", "fdat c Obzor804"),
    (correction_array[0::2], correction_array[1::2], "Измеренные значения", "Коррекционный коэфициент"),
    ]
    visualize_measurement_result(data_for_vizualization, num_cols = 3)
    return correction_array

def db_to_linear(db_value: float): #Перед записью в прибор старая программа переводит dB в линейный вид
    return 10 ** (db_value / 20.0)

def build_correction_array(measured_db_list: list, correction_db_list: list): #Формирует конечный массив для записи в прибор(перед записью, measured и correction переводятся из dB в linear), а так же значения этих 2 массивов чередуются
    if len(measured_db_list) != len(correction_db_list):
        raise ValueError("measured_db_list и correction_db_list должны быть одинаковой длины")
    result = []
    for meas_db, corr_db in zip(measured_db_list, correction_db_list):
        result.append(db_to_linear(meas_db))
        result.append(db_to_linear(corr_db))
    return result

def format_array_for_scpi_old_style(values: list): #Форматирует массив как старая программа.
    return ",".join(f"{float(value):.6E}" for value in values)


def receiver_number_from_trace(trace_name: str):    #Возвращает номер приёмника для команды SERV:RECn:LIN:DATA.
    kind = trace_name[0].upper()
    number = int(trace_name[1:])
    if kind == "T":
        return 1 + (number - 1) * 2
    if kind == "R":
        return 2 + (number - 1) * 2
    raise ValueError(f"Неизвестная трасса: {trace_name}")

def send_correction_array(device, port: str, correction_array: list, dry_run: bool = True): #Отправляет массив коррекции в SN9000
    receiver_number = receiver_number_from_trace(port)
    payload = format_array_for_scpi_old_style(correction_array)
    print("Trace:", port)
    print("Receiver number:", receiver_number)
    print("Количество чисел:", len(correction_array))
    print(f"SERV:REC{receiver_number}:LIN:DATA {payload}")
    if dry_run:
        print("DRY RUN: команда не отправлена в прибор!!!!!!!!!!!!!!!!!", 
              "Если хотите записывать данные, то передайте фукции send_correction_array False",
              sep = "\n")
        return
    device.write(f"SERV:REC{receiver_number}:LIN:DATA {payload}")
    time.sleep(2.0)# Старый код ждал 4 секунды после записи.

def what_ports_we_need_to_measure():#Функция для отбора портов котороые нам нужно измерить(проты имеется в виду T1, R1, T2, ...)
    ports_for_measure = []
    for i in list(ENUMERATION_OF_PORTS):
        if ENUMERATION_OF_PORTS[i] == 1:
            ports_for_measure.append(i) 
    return ports_for_measure

def main_cycle_changing_r_t():# Цикл для изменения порта R и T, эти порты мы берем из .ini файла
    ports_for_measure = what_ports_we_need_to_measure()

    for port in ports_for_measure:
        input(f"Подключте пожалуйста порт {port[1:]} и после введите что то в консоль")
        if port == "T":
            setup_for_measurement_t(port)
        elif port == "R":
            setup_for_measurement_r(port)
        device_setup()
        correction_values = measure_port(port)
        send_correction_array(device, port, correction_values, False)


try:
    # device_or_generator_func('TCPIP0::localhost::5026::SOCKET')
    # device_or_generator_func('TCPIP0::localhost::5025::SOCKET')
    ini_config = load_ini(r"C:\adc-corrector-develop\adc-corrector-develop\System\SN9000-10_2.ini")
    NUMBER_OF_POINTS = ini_config["zones"][-1]["end"] - ini_config["zones"][0]["begin"] + 1 #Количество точек во всех сегментах(у нас есть 2 мощности(min, max) и между ними мы делаем столько измерений сколько точек)
    MAX_POWER = ini_config["power_up"]
    MIN_POWER = ini_config["power_down"]
    ENUMERATION_OF_PORTS = ini_config["receivers"]
    device = open_scpi_resource(DEVICE_ADDRESS)#device_generator_adreses[1]
    generator = open_scpi_resource(GENERATOR_ADDRESS)#device_generator_adreses[0]
    device_idn, generator_idn = get_info() 
    print(device_idn, 
          generator_idn, 
          sep="\n")
    main_cycle_changing_r_t()
except pyvisa.errors.VisaIOError as e:
    print(e)
    print("Ошибка связанная с портом, pyvisa или чем то подобным")

