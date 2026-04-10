import pyvisa

rm = pyvisa.ResourceManager() # '@py' необходим для принудительного использования бэкенда не NI-VISA, а pyvisa-py
print(rm.list_resources('TCPIP?*')) #'?*' это фильтр необходимый для обнаружения нашего адреса устройства, так как бех него будут искаться только приборы, чьи имена заканчиваются на ::INSTR, а наше заканчивется на ::SOCKET
# Если мы хотим только ::SOCKET, то испольхзуем вот такой фильтр 'TCPIP?*'

device_generator_adreses = ["", ""] #Список для записи адрессов generator и device
list_of_adc = ["SN9000-10"] #Список для устройств которые являются device, а не generator, и это значит мы должны спрашивать количество их портов

def device_or_generator_func(adres):#Эта функция нам нужна только для того что бы определить что за устройство мы подключили, generator или device
    instrument = rm.open_resource(adres)
    if instrument.query("*IDN?").split(", ")[1] in list_of_adc:#Тут мы разделяем строку которую нам возвращает *IDN?, и смотрим что это за устройство, есть лиона в списке list_of_adc
        device_generator_adreses[1] = adres
        instrument.close()
        return
    device_generator_adreses[0] = adres
    instrument.close()
    return 

def initialization():#Функиция для инициализации приборов
    print(device.query("*IDN?"))
    quantity_of_ports = device.query(":SERV:PORT:COUN?")
    print(quantity_of_ports)
    print(device.query("syst:err?"))
    print(generator.query("*IDN?"))
    print(generator.query("syst:err?"))
    return 

list_of_segment_data = [5,0,1,0,0,0,2,936000000,936000000,2,1000,936000000,936000000,2,10000]
def device_setup():
    device.query("syst:pres")
    device.query("trigger:source BUS")
    device.query("init:cont 1")
    device.query("trigger:wait WAIT")
    device.query("sens:rosc:sour EXT")
    device.query("SENS:SWE:TYPE SEGM")
    device.query(f"SENS:SEGM:DATA {list_of_segment_data}")
    device.query("trig:sing")

generator_port = "R2"
device_port = "T1"
def swithing_t_r(latest_device_port):#latest_device_port это T ИЛИ R n-ого порядка до котрого мы доходим, задаётся оно в настройках программы либо в ini файле для каждого device
    if device_port == latest_device_port:#Функция swithing_t_r нужна для переключения T и R котроые мы ихмеряем, то есть мы идем для device T1, R1, T2, R2 и тд, а для generator R2, T2, R2, T2 и тд
        return
    generator.query("syst:pres")
    generator.query(f"calc:par1:def {generator_port}")
    generator.query("calc:par1:spor 2")
    device.query("calc:par1:spor 2")
    device.query(f"calc:par1:def {device_port}")
    device.query("calc:par1:spor 2")
    if generator_port[0] == "R" and device_port[0] == "T":
        generator_port = "T2"
        device_port = f"R{device_port[1]}"
    else:
        generator_port = "R2"
        device_port = f"T{int(device_port[1]) + 1}"

try:
    device_or_generator_func('TCPIP0::localhost::5026::SOCKET')
    device_or_generator_func('TCPIP0::localhost::5025::SOCKET')
    device = rm.open_resource(device_generator_adreses[1])
    generator = rm.open_resource(device_generator_adreses[0])
    device.timeout = 5000
    device.write_termination = '\n'   # Отправлять \n после каждой команды
    device.read_termination = '\n'    # Ждать \n в конце ответа
    generator.timeout = 5000
    generator.write_termination = '\n'   # Отправлять \n после каждой команды
    generator.read_termination = '\n'    # Ждать \n в конце ответа
    initialization()#device_or_generator принимает значение 1 
except pyvisa.errors.VisaIOError as e:
    print("Ошибка связанная с портом, pyvisa или чем то подобным")

# SN9000-10 15.866082s syst:pres
# SN9000-10 15.866114s trigger:source BUS
# SN9000-10 15.866128s init:cont 1
# SN9000-10 15.866140s trigger:wait WAIT
# SN9000-10 15.866152s sens:rosc:sour EXT

# Obzor804 15.894331s syst:err?
# Obzor804 15.896987s 0,"No error"

# SN9000-10 16.374300s SENS:SWE:TYPE SEGM
# SN9000-10 16.374401s SENS:SEGM:DATA 5,0,1,0,0,0,2,936000000,936000000,2,1000,936000000,936000000,2,10000
# SN9000-10 16.876104s trig:sing
# SN9000-10 16.876177s *OPC?
# SN9000-10 16.891749s 1

# Obzor804 21.871429s syst:pres
# Obzor804 21.871487s calc:par1:def R2
# Obzor804 21.871500s calc:par1:spor 2

# SN9000-10 22.338480s syst:pres
# SN9000-10 22.338528s calc:par1:def T1
# SN9000-10 22.338542s calc:par1:spor 2

# Obzor804 22.370561s trigger:source BUS
# Obzor804 22.370599s init:cont 1
# Obzor804 22.370612s trigger:wait WAIT
# Obzor804 22.370624s outp:state 1

# SN9000-10 22.838235s sens:rosc:sour EXT
# SN9000-10 22.838270s outp:state 1
# SN9000-10 22.838281s trigger:source BUS
# SN9000-10 22.838293s init:cont 1
# SN9000-10 22.838303s trigger:wait WAIT

# SN9000-10 22.838315s serv:rec:corr:state 0
# SN9000-10 22.838351s serv:rec:corr:state?
# SN9000-10 22.943659s 0
# SN9000-10 22.943824s serv:rec:lin:state 0
# SN9000-10 22.943881s serv:rec:lin:state?
# SN9000-10 22.944895s 0


# Условие перехода. При получении команды SCPI, если источник триггера Шина.
# SN9000-10 10.698360s trigger:source BUS(Выбирает источник триггера для запуска сканирования. INTernal Внутренний
# EXTernal Внешний (аппаратный вход триггера)
# MANual Ручной (интерфейс пользователя)
# BUS Шина (программный запуск))
# SN9000-10 10.698389s init:cont 1 (Устанавливает или считывает состояние ВКЛ/ВЫКЛ для режима инициации
# канала "Непрерывно".)
# SN9000-10 10.698416s trigger:wait WAIT
# Obzor804 14.340112s trigger:source BUS
# Obzor804 14.340147s init:cont 1
# Obzor804 14.340158s trigger:wait WAIT
# Obzor804 14.340170s outp:state 1
# SN9000-10 14.827869s outp:state 1