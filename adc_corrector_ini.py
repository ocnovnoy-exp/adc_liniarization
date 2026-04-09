import pyvisa
rm = pyvisa.ResourceManager() # '@py' необходим для принудительного использования бэкенда не NI-VISA, а pyvisa-py
print(rm.list_resources('TCPIP?*')) #'?*' это фильтр необходимый для обнаружения нашего адреса устройства, так как бех него будут искаться только приборы, чьи имена заканчиваются на ::INSTR, а наше заканчивется на ::SOCKET
# Если мы хотим только ::SOCKET, то испольхзуем вот такой фильтр 'TCPIP?*'

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
        instrument.close()
        return 1 #Если это device, то вернётся 1
    print(instrument.query("syst:err?"))
    instrument.close()
    return 0 #Если это generator, то вернётся 0

try:
    initialization('TCPIP0::localhost::5025::SOCKET')
except pyvisa.errors.VisaIOError as e:
    print("Ошибка связанная с портом, pyvisa или чем то подобным")

