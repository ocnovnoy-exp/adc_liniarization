import pyvisa
from configparser import ConfigParser
import time
import matplotlib.pyplot as plt


rm = pyvisa.ResourceManager() # '@py' необходим для принудительного использования бэкенда не NI-VISA, а pyvisa-py
print(rm.list_resources('TCPIP?*')) #'?*' это фильтр необходимый для обнаружения нашего адреса устройства, так как бех него будут искаться только приборы, чьи имена заканчиваются на ::INSTR, а наше заканчивется на ::SOCKET
# Если мы хотим только ::SOCKET, то испольхзуем вот такой фильтр 'TCPIP?*'

device_generator_adreses = ["", ""] #Список для записи адрессов generator и device
list_of_adc = ["SN9000-10"] #Список для устройств которые являются device, а не generator, и это значит мы должны спрашивать количество их портов

def open_scpi_resource(address: str):
    inst = rm.open_resource(address)
    inst.timeout = 5000
    inst.write_termination = "\n" # Отправлять \n после каждой команды
    inst.read_termination = "\n" # Ждать \n в конце ответа
    return inst

def device_or_generator_func(adres):#Эта функция нам нужна только для того что бы определить что за устройство мы подключили, generator или device
    instrument = rm.open_resource(adres)
    if instrument.query("*IDN?").split(", ")[1] in list_of_adc:#Тут мы разделяем строку которую нам возвращает *IDN?, и смотрим что это за устройство, есть лиона в списке list_of_adc
        device_generator_adreses[1] = adres
        instrument.close()
        return
    device_generator_adreses[0] = adres
    instrument.close()
    return 

def load_ini(path: str):
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
        "receivers" : {reciver_tuple[0][8:]: int(reciver_tuple[1]) for reciver_tuple in cfg.items("ReceiverSettings")}# Получаем перечень приемников из .ini файла, получаем пару {'T1': 1, ..., 'R32': 0}
    }

def get_info():#Получение информации от приборов, имя, версию и тд.
    dev_idn, gen_idn = [], []
    dev_idn = device.query("*IDN?").split(", ")
    print(dev_idn)
    quantity_of_ports = device.query(":SERV:PORT:COUN?")
    print(quantity_of_ports)
    print(device.query("syst:err?"))
    gen_idn = generator.query("*IDN?").split(", ")
    print(gen_idn)
    print(generator.query("syst:err?"))
    return dev_idn, gen_idn

list_of_segment_data = [5,0,1,0,0,0,2,936000000,936000000,2,1000,936000000,936000000,2,10000]
def device_setup():# Функция в которой мы задаём сегменты для измерения
    device.write("syst:pres")
    device.write("trigger:source BUS")
    device.write("init:cont 1")
    device.write("trigger:wait WAIT")
    device.write("sens:rosc:sour EXT")
    device.write("SENS:SWE:TYPE SEGM")
    device.write(f"SENS:SEGM:DATA {",".join(str(num) for num in list_of_segment_data)}")
    device.write("trig:sing")

generator_port = "R2"
device_port = "T1"

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

def switching_on_t(port):# Мы передаём сюда порт(когда меняем с R на T) устройства которого мы проверяем, device_port
    generator_switching_setup()
    device.write("syst:pres")
    device.write(f"calc:par1:def {port}")
    generator.write("trigger:source BUS")
    generator.write("init:cont 1")
    generator.write("trigger:wait WAIT")
    device.write("calc:par1:spor 2")
    generator.write("outp:state 1")
    device_switching_setup()

def switching_on_r(port):# Мы передаём сюда порт(когда меняем с T на R) устройства которого мы проверяем, device_port
    generator_switching_setup()
    device.write("syst:pres")
    device.write(f"calc:par1:def {port}")
    generator.write("trigger:source BUS")
    generator.write("init:cont 1")
    generator.write("trigger:wait WAIT")
    device.write("calc:par1:spor 1")
    generator.write("calc:par1:def T2")
    generator.write("outp:state 0")
    device_switching_setup()

def wait_opc(instrument):
    answer_on_opc = instrument.query("*OPC?").strip()
    if answer_on_opc != "1":
        raise RuntimeError(f"Неожиданный ответ на *OPC?, а именно: {answer_on_opc}")

# def syst_err(instrument):
#     answer_on_opc = instrument.query("syst:err?").strip()
#     if answer_on_opc != '0,"No error"':
#         raise RuntimeError(f"Неожиданный ответ от syst:err?: {answer_on_opc}")

power_down = -45.000000
power_up = 10.000000 #Эти 2 значения тоже должны браться из ini файла
def grid_of_powers(power_up: float, power_down: float, points_of_power: int = 125):#Изменение мощности происходит просто определением дельты, и уже после этого мы идем от наибольшей мозности отнимая значение дельты умноженной на номер шага 
    delta_power = (power_up - power_down) / (points_of_power - 1)
    return [power_up - delta_power * i for i in range(points_of_power)]

def zone_for_point(num_of_point: int, ini_conf: dict):#Функця определяет какое bandwidth для этой точки(в каком из 3 сегментов находится точка)
    for zones_conf in ini_conf.get("zones"):#функция возвращает настройки для сегмента в котором находится точка
        if zones_conf.get("begin") <= num_of_point <= zones_conf.get("end"):
            if num_of_point == zones_conf.get("begin"):
                device.write("sens1:aver:stat 0")
                generator.write("sens1:aver:stat 0")
            return zones_conf
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
    instrument.write("trig:sing")
    wait_opc(instrument)

def taking_fdat(instrument):#Эта функция берет список после CALC:DATA:FDAT?
#    syst_err(instrument)
    instrument.write("calc:parameter1:select")
    values = [float(i.strip()) for i in instrument.query("CALC:DATA:FDAT?").split(",")]
    print(instrument, values[0])
    return values

def reduce_fdat(val: list):
    average_weignt = 0
    for i in range(0, len(val), 2):
        average_weignt += val[i]
    return average_weignt / (len(val) / 2)

def setting_scan_type(instrument, powers_grid: list, num_of_point: int, ini_conf: dict):#Функция необходимая для задания мощности и отправки SENS:SEGM:DATA 2 раза, с bandwidth = 1000 и той что мы берем их .ini файла
    power = powers_grid[num_of_point]
    zone = zone_for_point(num_of_point, ini_conf)
    print(f"SOURce1:POWer {power:.6e}       {zone['bandwidth']}      {num_of_point}")
    instrument.write(f"SOURce1:POWer {power:.6e}")
    set_segment(instrument, ini_conf["frequency"], 1000)
    set_segment(instrument, ini_conf["frequency"], zone["bandwidth"])

def compute_correction(etalon_i, measured_i, etalon_0, measured_0): #Формула correction из старой программы: corr_i = (etalon_i - measured_i) - (etalon_0 - measured_0)
    return (etalon_i - measured_i) - (etalon_0 - measured_0)

def correction(num_in_grid_of_power: int, list_of_values: list): #Считаем коэффициенты для коррекции
    if num_in_grid_of_power == 0:
        correction = 0.0
    else:
        correction = compute_correction(
            etalon_i=list_of_values[0][num_in_grid_of_power],
            measured_i=list_of_values[1][num_in_grid_of_power],
            etalon_0=list_of_values[0][0],
            measured_0=list_of_values[1][0],
        )
    return correction

def vizualization_of_numbers(x, y): # Функция для визуализации массива данных котороые мы получаем
    plt.scatter(x, y)
    plt.show()

#выбор того кому передаём source1:power зависит от того кто является R
dev_gen_val = [[], []]
def sens_data(instrument):#Эта функция нужна для того что бы пройтись по всем мощностям и записать значения корректировки в массив
    power_grid = grid_of_powers(ini_config["power_up"], ini_config["power_down"], points_of_power=125)
    print(power_grid)
    correction_list = [[], []]
    for n in range(len(power_grid)):
        setting_scan_type(instrument, power_grid, n, ini_config)
        dev_val = taking_fdat(device)
        gen_val = taking_fdat(generator)
        dev_gen_val[1].append(reduce_fdat(dev_val))
        dev_gen_val[0].append(reduce_fdat(gen_val))
        correction_list[1].append(correction(n, dev_gen_val)) #Считаем коэффициенты для коррекции
        correction_list[0].append(power_grid[n]) #Добавляем в конечный список мощности, так же как это было в изначальной программе  power0, corr0, power1, corr1,...
        correction_list[1][n] = db_to_linear(correction_list[1][n])#Перед записью в прибор старая программа переводит dB в линейный вид
        correction_list[0][n] = db_to_linear(correction_list[0][n])
    vizualization_of_numbers(correction_list[1], correction_list[0])
    vizualization_of_numbers(power_grid, dev_gen_val[1])
    vizualization_of_numbers(power_grid, dev_gen_val[0])
    return correction_list

def db_to_linear(db_value: float): #Перед записью в прибор старая программа переводит dB в линейный вид
    return 10 ** (db_value / 20.0)

def build_correction_array(power_db_list, correction_db_list): #Формирует конечный массив для записи в прибор(перед записью, power и correction переводятся из dB в linear)
    if len(power_db_list) != len(correction_db_list):
        raise ValueError("power_db_list и correction_db_list должны быть одинаковой длины")
    result = []
    for power_db, corr_db in zip(power_db_list, correction_db_list):
        result.append(db_to_linear(power_db))
        result.append(db_to_linear(corr_db))
    return result

def format_array_for_scpi_old_style(values): #Форматирует массив как старая программа.
    return ",".join(f"{float(value):.6E}" for value in values)


def receiver_number_from_trace(trace_name: str):    #Возвращает номер приёмника для команды SERV:RECn:LIN:DATA.
    kind = trace_name[0].upper()
    number = int(trace_name[1:])
    if kind == "T":
        return 1 + (number - 1) * 2
    if kind == "R":
        return 2 + (number - 1) * 2
    raise ValueError(f"Неизвестная трасса: {trace_name}")


def send_correction_array(device, trace_name: str, correction_array, dry_run: bool = True): #Отправляет массив коррекции в SN9000
    receiver_number = receiver_number_from_trace(trace_name)
    payload = format_array_for_scpi_old_style(correction_array)
    command = f"SERV:REC{receiver_number}:LIN:DATA {payload}"
    print("\nПодготовка отправки массива коррекции")
    print("Trace:", trace_name)
    print("Receiver number:", receiver_number)
    print("Количество чисел:", len(correction_array))
    if dry_run:
        print("DRY RUN: команда не отправлена в прибор.")
        return
    device.write(command)
    #time.sleep(4.0)# Старый код ждал 4 секунды после записи.
    #syst_err(device)#, "after write correction array"

list_port = [[1, 1], [1, 1]] #Нужно добавить функцию для чтения ini файлов, из них в этот массив должны складываться какие R и T мы хотим посмотреть 
def initialization_and_switching_port(list_port):#Функция initialization_and_swithing_port нужна для выбора следующего порта и переключения T и R котроые мы измеряем, то есть мы идем для device T1, R1, T2, R2 и тд, а для generator R2, T2, R2, T2 и тд
    for i in range(len(list_port)):
        if list_port[i][0] == 1 or list_port[i][1] == 1:
            input(f"Подключите 2 порт {generator_idn[1]} с {i + 1} портом {device_idn[1]}, а после введите любой символ")
        for j in range(len(list_port[i])):
            if list_port[i][j] == 1 and j == 0:
                device_port = f"T{i + 1}"
                switching_on_t(device_port)
            elif list_port[i][j] == 1 and j == 1:
                device_port = f"R{i + 1}"   
                switching_on_r(device_port)
    return device_port

try:
    # device_or_generator_func('TCPIP0::localhost::5026::SOCKET')
    # device_or_generator_func('TCPIP0::localhost::5025::SOCKET')
    device = open_scpi_resource('TCPIP0::localhost::5026::SOCKET')#device_generator_adreses[1]
    generator = open_scpi_resource('TCPIP0::localhost::5025::SOCKET')#device_generator_adreses[0]
    device_idn, generator_idn = get_info() 
    ini_config = load_ini(r"C:\adc-corrector-develop\adc-corrector-develop\System\SN9000-10_2.ini")
    device_setup()
    switching_on_t("T1")
    all_values = sens_data(generator, ini_config["power_up"], ini_config["power_down"])
    print(all_values)
except pyvisa.errors.VisaIOError as e:
    print(e)
    print("Ошибка связанная с портом, pyvisa или чем то подобным")

