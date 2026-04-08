import pyvisa
rm = pyvisa.ResourceManager() # '@py' необходим для принудительного использования бэкенда не NI-VISA, а pyvisa-py
#print(rm.list_resources('TCPIP?*')) '?*' это фильтр необходимый для обнаружения нашего адреса устройства, так как бех него будут искаться только приборы, чьи имена заканчиваются на ::INSTR, а наше заканчивется на ::SOCKET
# Если мы хотим только ::SOCKET, то испольхзуем вот такой фильтр 'TCPIP?*'
try:
    my_instrument = rm.open_resource('TCPIP0::localhost::5025::SOCKET')
    my_instrument.timeout = 5000
    my_instrument.write_termination = '\n'   # Отправлять \n после каждой команды
    my_instrument.read_termination = '\n'    # Ждать \n в конце ответа
    print(my_instrument.query("*IDN?"))
except pyvisa.errors.VisaIOError as e:
    print("Ошибка связанная с портом, pyvisa или чем то подобным")
my_instrument.close()