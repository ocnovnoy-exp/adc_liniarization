import pyvisa
rm = pyvisa.ResourceManager() # '@py' необходим для принудительного использования бэкенда не NI-VISA, а pyvisa-py
print(rm.list_resources('TCPIP?*')) #'?*' это фильтр необходимый для обнаружения нашего адреса устройства, так как бех него будут искаться только приборы, чьи имена заканчиваются на ::INSTR, а наше заканчивется на ::SOCKET
# Если мы хотим только ::SOCKET, то испольхзуем вот такой фильтр 'TCPIP?*'

device_generator = ["", ""] #Список для записи адрессов generator и device
list_of_adc = ["SN9000-10"] #Список для устройств которые являются device, а не generator, и это значит мы должны спрашивать количество их портов

def initialization(instrument_adres):#Функиция для инициализации приборов
    instrument = rm.open_resource(instrument_adres)
    instrument.timeout = 5000
    instrument.write_termination = '\n'   # Отправлять \n после каждой команды
    instrument.read_termination = '\n'    # Ждать \n в конце ответа
    print(instrument.query("*IDN?"))
    if instrument.query("*IDN?").split(", ")[1] in list_of_adc: #Тут мы разделяем строку которую нам возвращает *IDN?, и смотрим что это за устройство
        quantity_of_ports = instrument.query(":SERV:PORT:COUN?")
        print(quantity_of_ports)
        print(instrument.query("syst:err?"))
        device_generator[1] = instrument_adres
        instrument.close()
        return 
    print(instrument.query("syst:err?"))
    device_generator[0] = instrument_adres
    instrument.close()
    return 

try:
    initialization('TCPIP0::localhost::5025::SOCKET')#device_or_generator принимает значение 1 
except pyvisa.errors.VisaIOError as e:
    print("Ошибка связанная с портом, pyvisa или чем то подобным")

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