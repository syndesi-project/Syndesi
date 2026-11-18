# Adapters de bus (I2C, SPI) et ponts (bridges)

Ce qui est implémenté, et pourquoi. La section HID en fin de document reste une
proposition.

## Objectif

Un Adapter par type de bus (IP, SerialPort, I2C, SPI, HID…), quel que soit ce qui le
fournit physiquement : le bus natif de la machine, un MCP2221, une carte sur mesure qui
traduit du série en SPI, etc. Les drivers de capteurs ne dépendent que de l'adapter.

```python
I2C("/dev/i2c-1", address=0x48)              # bus natif (Linux)
I2C(MCP2221(HID(...)), address=0x48)         # bus fourni par un pont
SPI("/dev/spidev0.0")
SPI(MaCarte(Delimited(SerialPort("/dev/ttyUSB0", 115200))), cs=1)
SerialPort(MaCarte(...), 9600)               # un pont peut aussi fournir un port série
```

## Rappels sur l'architecture

- **Adapter** = `AdapterBackend` (I/O) + `Framer` → `AdapterEngine`. Produit un flux de
  frames.
- **Protocol** = `ProtocolBackend` → `ProtocolEngine`, branché sur l'adapter via
  `FrameSink`.
- **Driver** = code utilisateur bloquant, toujours au sommet.
- Tous les engines tournent sur **un seul thread, le reactor**, qui surveille des fd avec
  `select`. Règle clé : depuis le reactor, **on n'attend jamais le futur d'un autre
  engine** (deadlock).

## Deux mécanismes, un rôle chacun

- **Réception : tout est un fd.** Le reactor ne surveille que des fd. Un transport qui
  n'en a pas (Visa, série sous Windows, tout ce qui passe par un pont) reçoit ses données
  d'un autre thread, qui les dépose dans une **`FragmentQueue`** : une socketpair et une
  file, c'est-à-dire un fd simulé. `ThreadedReader` = `FragmentQueue` + une boucle de
  lecture.
- **Écriture : un futur si elle ne peut pas se faire sur le reactor.**
  `AdapterBackend.write()` peut renvoyer un `Future[None]`. L'engine termine l'écriture
  quand ce futur l'est, ou la fait échouer avec son erreur. C'est ce qui permet de
  confier une écriture à un pont sans que le reactor l'attende.

Les erreurs d'écriture (un NACK I2C…) remontent donc à l'appelant de `write()`, sans
fermer l'adapter. Faire passer aussi les écritures par le fd simulé (écriture sans
attente) aurait obligé à transporter les erreurs dans le flux de lecture, avec leur
propre buffer et un `FrameSink.on_error` : plus compliqué que le futur.

## Ponts

Un pont est le **driver d'un convertisseur**. Il hérite d'une interface par bus fourni
et l'implémente en code bloquant ordinaire :

```python
class MaCarte(Driver, I2CBridge, SPIBridge, SerialBridge):
    def __init__(self, adapter):
        self._protocol = Delimited(adapter)

    def i2c_transfer(self, address, data, read_length):
        return bytes.fromhex(self._protocol.query(f"I2C {address} {data.hex()} {read_length}"))

    def spi_transfer(self, cs, data):
        return bytes.fromhex(self._protocol.query(f"SPI {cs} {data.hex()}"))
    ...
```

- Chaque pont a **son propre thread** (`Bridge.run`), qui exécute ses méthodes une à
  une. C'est ce qui lui permet de bloquer : le reactor n'exécute jamais de code de pont,
  il reste libre de livrer les réponses que le pont attend. Ce thread sérialise aussi les
  utilisateurs du pont (plusieurs adresses I2C, un SerialPort…), sans verrou.
- Le thread démarre au premier appel et s'arrête quand le pont est libéré par le garbage
  collector, ou avec `close_bridge()`.
- Un pont peut proposer d'autres méthodes de driver (GPIO du MCP2221…).
- Interfaces : `I2CBridge.i2c_transfer(address, data, read_length)`,
  `SPIBridge.spi_transfer(cs, data)`, `SerialBridge.serial_configure/write/read`.

### Les bus natifs sont des ponts

`LinuxI2C` (`/dev/i2c-N`, ioctl `I2C_RDWR`) et `LinuxSPI` (`/dev/spidevB.C`, ioctl
`SPI_IOC_MESSAGE`) sont des ponts comme les autres, dont le convertisseur est le noyau.
Un ioctl bloque pendant toute la transaction (≈ 400 ms pour une EEPROM de 4 ko à
100 kHz), il a donc sa place sur le thread du pont et pas sur le reactor.

- `I2C("/dev/i2c-1", ...)` crée le `LinuxI2C` de ce chemin, partagé par toutes les
  adresses du même bus (`WeakValueDictionary`). Même chose pour `SPI("/dev/spidevB.C")`,
  un `LinuxSPI` par bus B.
- Le fichier s'ouvre à la première transaction et se ferme avec `close_bridge()` ou au
  garbage collector. L'`open()` d'un adapter ne touche pas au bus, partagé.
- Mode, horloge et bits par mot du SPI se règlent par chip select, comme dans le noyau :
  `SPI("/dev/spidev0.1", mode=3, speed_hz=500_000)`. Deux composants d'un même bus
  peuvent donc avoir des modes différents. `None` garde la configuration actuelle du
  périphérique. `LinuxSPI(0, mode=..., ...)` donne des valeurs par défaut au bus entier.
  Avec un pont utilisateur, ces réglages sont refusés : c'est son driver qui configure
  son bus.
- Pas d'I2C/SPI natif générique sous Windows/macOS : une chaîne y lève
  `AdapterConfigurationError`, il faut un pont.
- Testés avec un faux ioctl uniquement (`tests/bridges/test_linux.py`), à valider sur
  du vrai matériel.

## I2C et SPI

Sur ces bus rien n'arrive sans être demandé : **chaque écriture est une transaction, et
ce qui est lu pendant celle-ci est sa réponse**. `BusBackend` (commun aux deux) :

1. `write()` confie la transaction au pont et renvoie son futur ;
2. sur le thread du pont, la transaction s'exécute et sa réponse est déposée dans la
   `FragmentQueue` **avant** que le futur se termine ;
3. le reactor la lit comme n'importe quelle donnée reçue (`TrivialFramer` : un fragment
   = une frame).

`query()` (écriture puis lecture `LAST_WRITE`) trouve donc toujours la réponse. Events,
trace, `AsyncI2C`/`AsyncSPI` et protocoles posés dessus fonctionnent comme sur les autres
adapters.

### I2C

```python
i2c = I2C("/dev/i2c-1", address=0x48)
i2c.write(b"\x01\x60")                   # écriture seule, pas de frame
i2c.write(b"")                           # adresse seule : sonde le périphérique
i2c.transfer(b"\x00", read_length=2)     # écriture, repeated start, lecture → bytes
i2c.transfer(read_length=2)              # lecture seule
i2c.query(I2CTransfer(b"\x00", 2))       # la même chose, ce qu'écrirait un protocole
```

La longueur à lire doit accompagner l'écriture jusqu'au pont. `I2CTransfer` est une
**sous-classe de `bytes`** qui porte `read_length` : le `DataT` reste `bytes`, rien ne
change dans l'engine, et un protocole posé sur `I2C` peut produire lui-même des
`I2CTransfer`. `read()` n'est pas surchargé, pour ne pas entrer en conflit avec
`read(timeout, scope, ...)`.

Descripteur : `i2c:bus@adresse`, par exemple `i2c:/dev/i2c-1@0x48` ou
`i2c:MCP2221@0x48`. Les chaînes d'un bus natif sont reconnues par `auto_adapter()`.

### SPI

Full duplex : les octets reçus pendant une écriture sont une frame, autant que d'octets
écrits. `spi.query(data)` ou son alias `spi.transfer(data)` les renvoie. Une simple
`write()` les laisse dans le buffer, où un `read()` les trouve.

Descripteur : `spi:bus.cs`, par exemple `spi:/dev/spidev0.1` ou `spi:MaCarte.1`. Les
chaînes d'un bus natif sont reconnues par `auto_adapter()`.

### Nom d'un pont

Le `bus` d'un descripteur est le nom du pont : le nom de sa classe, suivi de `#2`,
`#3`… pour les autres instances vivantes en même temps. Chaque pont accepte un mot-clé
`name` pour le choisir, sans que son auteur ait à le déclarer :

```python
gauche = MaCarte(Delimited(IP("10.0.0.2", 4242), "\n"), name="gauche")
I2C(gauche, 0x0F)   # i2c:gauche@0x0f
```

Un pont dont le `__init__` a déjà un paramètre `name` le garde pour lui, son nom reste
celui par défaut (ou `set_bridge_name()`).

## Coût d'un nouveau bus ou d'un nouveau pont

- Un bus : `XBackend` (hérite de `BusBackend`, n'implémente que `transfer()`), `X`,
  `AsyncX`. **3 classes.**
- Un pont : **1 classe**, son driver.

## Pile complète

```text
Driver du capteur            bloquant, toujours au sommet
 └ Protocol (optionnel)      ex. Registers
    └ I2C / SPI              Adapter de bus
       └ Bridge              thread propre, bloquant (ou natif : LinuxI2C, LinuxSPI)
          └ Protocol (opt.)  ex. Delimited, Modbus
             └ Adapter       SerialPort, HID, IP…
```

## Points ouverts

- Sémantique des timeouts entre le bus et les couches du dessous : le pont a les siens,
  l'écriture n'a pas de timeout propre.
- Le CLI et l'UI ne connaissent que les bus natifs : dans l'UI, le champ `bus` n'accepte
  qu'un chemin, on ne peut pas encore y brancher un pont.
- Option écartée pour l'instant : remplacer le reactor par une boucle asyncio. Gain de
  vocabulaire, mais réécriture des engines pour une complexité (framing, scopes,
  auto-open) qui resterait la même.

## CLI et UI

- `auto_adapter()` reconnaît `i2c:/dev/i2c-1@0x48` et `spi:/dev/spidev0.1`, et refuse
  un nom de pont : un pont est un objet, il se passe à l'adapter.
- CLI : `syndesi term i2c /dev/i2c-1 0x48 --read 2` écrit chaque ligne puis lit 2
  octets, `syndesi term spi /dev/spidev0.0` affiche les octets reçus pendant chaque
  envoi. Format hex et pas de terminaison par défaut, `--list` liste les bus. Une erreur
  du bus (NACK…) est affichée au lieu d'arrêter le terminal.
- UI : `I2C`, `SPI` et leurs versions async sont dans la bibliothèque, le champ `bus`
  propose les bus de la machine (`list_buses()`). Pour un I2C, la ligne Query a un champ
  `read` : la longueur lue après l'écriture.

## Prochaine étape : HID (proposition)

- **HID est un Adapter**, pas un Protocol sur USB : sous Windows et macOS l'OS possède
  les interfaces HID, HID existe aussi en Bluetooth et en I²C, et un Protocol est
  terminal.
- Via **hidapi**, avec un `ThreadedReader` (comme Visa).
- **Reports bruts** : un `read()` hidapi = un report = un fragment, **`FragmentSC` par
  défaut**. `read_once` lit un seul report.
- **Feature reports** exposés (`send_feature_report()`, `get_feature_report()`), passés
  par l'engine sous forme de commandes (hidapi n'est pas garanti thread-safe).
- **Report ID en écriture** : `report_id=0` par défaut (l'adapter ajoute l'octet),
  `report_id=None` pour le mode transparent.
- Pas de codec dans HID : les ponts HID-UART (CP2110…) sont des ponts (`SerialBridge`).
- `list_usb_devices()` générique, extra optionnel `syndesi[hid]`, import protégé dans
  `auto.py`.
- Ensuite : un pont `MCP2221` (I2C + GPIO sur HID) en exemple.
