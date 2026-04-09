import pyvisa
rm = pyvisa.ResourceManager() # '@py' необходим для принудительного использования бэкенда не NI-VISA, а pyvisa-py
print(rm.list_resources('TCPIP?*')) #'?*' это фильтр необходимый для обнаружения нашего адреса устройства, так как бех него будут искаться только приборы, чьи имена заканчиваются на ::INSTR, а наше заканчивется на ::SOCKET
# Если мы хотим только ::SOCKET, то испольхзуем вот такой фильтр 'TCPIP?*'

list_of_adc = ["SN9000-10"] #Список для устройств которые являются device, а не generator, и это значит мы должны спрашивать количество их портов
def initialization(instrument_adres):
    print(instrument_adres.query("*IDN?"))
    if instrument_adres.query("*IDN?").split(", ")[1] in list_of_adc: #Тут мы разделяем строку которую нам возвращает *IDN?, и смотрим что это за устройство
        quantity_of_ports = instrument_adres.query(":SERV:PORT:COUN?")
        print(quantity_of_ports)
    print(instrument_adres.query("syst:err?"))
    return

try:
    my_instrument = rm.open_resource('TCPIP0::localhost::5025::SOCKET')
    my_instrument.timeout = 5000
    my_instrument.write_termination = '\n'   # Отправлять \n после каждой команды
    my_instrument.read_termination = '\n'    # Ждать \n в конце ответа
    initialization(my_instrument)
except pyvisa.errors.VisaIOError as e:
    print("Ошибка связанная с портом, pyvisa или чем то подобным")
#my_instrument.close()
