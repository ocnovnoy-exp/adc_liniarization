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
    dev_idn, gen_idn = [], []
    print(dev_idn = device.query("*IDN?").split(", "))
    quantity_of_ports = device.query(":SERV:PORT:COUN?")
    print(quantity_of_ports)
    print(device.query("syst:err?"))
    print(gen_idn = generator.query("*IDN?").split(", "))
    print(generator.query("syst:err?"))
    return dev_idn, gen_idn

list_of_segment_data = [5,0,1,0,0,0,2,936000000,936000000,2,1000,936000000,936000000,2,10000]
def device_setup():
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

def switching_t_r(port):
    generator.write("syst:pres")
    generator.write("calc:par1:def R2")#В логах мы сначала передаем obzor что он R2, а затем что он T2, можно ли обойтись только тем что говорим, что он T2?
    generator.write("calc:par1:spor 2")# !!!!! надо разобарться что с этой командой, где 1, а где 2 ставится
    device.write("syst:pres")
    device.write(f"calc:par1:def {port}")
    if port[0] == "R":
        device.write("calc:par1:spor 1")
        generator.write("trigger:source BUS")
        generator.write("init:cont 1")
        generator.write("trigger:wait WAIT")
        generator.write("calc:par1:def T2")
        generator.write("outp:state 0")
    elif port[0] == "T":
        device.write("calc:par1:spor 2")
        generator.write("trigger:source BUS")
        generator.write("init:cont 1")
        generator.write("trigger:wait WAIT")
        generator.write("outp:state 1")
    device.write("sens:rosc:sour EXT")
    device.write("outp:state 1")
    device.write("trigger:source BUS")
    device.write("init:cont 1")
    device.write("trigger:wait WAIT")
    device.write("serv:rec:corr:state 0")
    device.query("serv:rec:corr:state?")
    device.write("serv:rec:lin:state 0")# Если запускать программу в режиме проверки, то тут будет не 0, а 1
    device.query("serv:rec:lin:state?")

power_up = -45.000000
power_down = 10.000000 #Эти 2 значения тоже должны браться из ini файла
def grid_of_powers(power_up: float, power_down: float, points_of_power: int = 125):#Изменение мощности происходит просто определением дельты, и уже после этого мы идем от наибольшей мозности отнимая значение дельты умноженной на номер шага 
    delta_power = (power_up - power_down) / (points_of_power - 1)
    return [power_up - delta_power * i for i in range(points_of_power)]


list_port = [[1, 1], [1, 1]] #Нужно добавить функцию для чтения ini файлов, из них в этот массив должны складываться какие R и T мы хотим посмотреть 
def switching_port(list_port):#Функция swithing_port нужна для переключения T и R котроые мы ихмеряем, то есть мы идем для device T1, R1, T2, R2 и тд, а для generator R2, T2, R2, T2 и тд
    for i in range(len(list_port)):
        if list_port[i][0] == 1 or list_port[i][0] == 1:
            input(f"Подключите 2 порт {generator_idn[1]} с {i} портом {device_idn[1]}, а после введите любой символ")
        for j in range(len(list_port[i])):
            if list_port[i][j] == 1 and j == 0:
                device_port = f"T{i + 1}"
                switching_t_r(device_port)
            elif list_port[i][j] == 1 and j == 1:
                device_port = f"R{i + 1}"   
                switching_t_r(device_port) 

    

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
    device_idn, generator_idn = initialization() 
except pyvisa.errors.VisaIOError as e:
    print("Ошибка связанная с портом, pyvisa или чем то подобным")

