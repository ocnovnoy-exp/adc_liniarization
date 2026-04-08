import pyvisa
rm = pyvisa.ResourceManager()
#print(rm.list_resources('TCPIP?*')) # '?*' это фильтр необходимый для обнаружения нашего адреса устройства, так как бех него будут искаться только приборы, чьи имена заканчиваются на ::INSTR, а наше заканчивется на ::SOCKET
# Если мы хотим только ::SOCKET, то испольхзуем вот такой фильтр 'TCPIP?*'
my_instrument = rm.open_resource('TCPIP0::localhost::5025::SOCKET')
my_instrument.write_termination = '\n'   # Отправлять \n после каждой команды
my_instrument.read_termination = '\n'    # Ждать \n в конце ответа
my_instrument.write("*IDN?")
print(my_instrument.read())