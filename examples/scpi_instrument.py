"""Control a SCPI instrument. Start drivers/fake_psu.py first, a simulated power supply"""

from syndesi import IP, SCPI

psu = SCPI(IP("127.0.0.1"))  # port 5025 and "\n" : SCPI knows its defaults

print(psu.query("*IDN?"))  # 'Syndesi,DemoPSU,0001,1.0'
psu.write("VOLT 3.3")
psu.write("OUTP ON")
print(float(psu.query("MEAS:VOLT?")))  # 3.3, more or less

psu.write("OUTP OFF")
psu.close()
