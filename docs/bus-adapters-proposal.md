# Proposition : HID, I2C, SPI et ponts (bridges)

Résumé d'une discussion de conception (novembre 2026). Rien n'est encore implémenté.

## Objectif

Avoir un Adapter par type de bus (IP, SerialPort, HID, I2C, SPI, USB…), quel que soit
le chip ou la carte qui le fournit physiquement : MCP2221, carte sur mesure qui
traduit du série en SPI, I2C natif d'une carte mère, etc.

## Rappels sur l'architecture actuelle

- **Adapter** = `AdapterBackend` (I/O) + `Framer` → `AdapterEngine`. Produit un flux de
  frames. Les protocoles se posent dessus.
- **Protocol** = `ProtocolBackend` pur (encode / push) → `ProtocolEngine`, branché sur
  l'adapter via `FrameSink`.
- **Driver** = code utilisateur bloquant, toujours au sommet.
- Tous les engines tournent sur **un seul thread, le reactor**. Règle clé : depuis le
  reactor, **on ne doit jamais attendre le futur d'un autre engine** (deadlock). Une I/O
  bloquante courte est tolérée (`SerialPortBackend.write()` le fait déjà).

## Décisions

### HID

- **HID est un Adapter**, pas un Protocol sur USB :
  - sous Windows et macOS, c'est l'OS qui possède les interfaces HID (libusb ne peut
    pas les réclamer) ;
  - HID existe aussi en Bluetooth et en I²C ;
  - un Protocol est terminal, on ne pourrait rien poser dessus.
- Implémentation via **hidapi** partout, avec un `ThreadedReader` (comme Visa).
- **Reports bruts** : un `read()` hidapi = un report = un fragment. **`FragmentSC` par
  défaut** (pas `Continuation`, qui recollerait des reports arrivant en rafale).
  `read_once` doit lire un seul report, pas drainer une rafale comme
  `VisaBackend._read_blocking`.
- **Feature reports** exposés (`send_feature_report()`, `get_feature_report()`), passés
  par l'engine sous forme de commandes (hidapi n'est pas garanti thread-safe).
- **Report ID en écriture** : `report_id=0` par défaut (l'adapter ajoute l'octet),
  `report_id=None` pour le mode transparent. Évite l'asymétrie de hidapi (lecture de
  64 octets sans ID, écriture de 65 octets avec ID).
- Pas de codec dans HID. Les ponts HID-UART (CP2110…) encapsulent les données dans les
  reports ; ce n'est pas le rôle d'une stop-condition, qui décide où la frame s'arrête et
  pas quels octets en font partie (et que Delimited/Modbus remplacent de toute façon).
  Ces ponts seront traités par des drivers ou par le mécanisme de bridge ci-dessous.
- `list_usb_devices()` générique : VID, PID, fabricant, produit, numéro de série,
  chemin.
- Extra optionnel `syndesi[hid]`, import protégé dans `auto.py`.

### I2C, SPI et ponts

- **Une seule classe d'adapter par bus** : `I2C`, `SPI`. Les drivers de capteurs ne
  dépendent que d'elle.
- Ce qui fournit le bus est un **pont** : `I2CBridge`, `SPIBridge` (classes de base).
  - Ponts **empilés** : `MCP2221`, carte sur mesure… Ce sont des **générateurs** : chaque
    `yield` envoie une donnée à la couche du dessous et récupère la réponse. Code
    lisible comme du séquentiel, mais non bloquant, sur le reactor, sans thread.
  - Ponts **natifs** : `LinuxI2C` (`/dev/i2c-N`, ioctl `I2C_RDWR`), `LinuxSPI`
    (`/dev/spidevX.Y`). Pas de couche en dessous, la méthode renvoie directement le
    résultat.
- **Le pont n'est pas un Driver** : un Driver bloque, un pont ne doit jamais bloquer
  (pas de `time.sleep()` ni de `query()` ; prévoir `yield Delay(...)`). Un pont peut
  quand même proposer des méthodes de type driver (ex. GPIO du MCP2221), sérialisées par
  le même engine.
- Le pont prend possession du flux de la couche du dessous (comme un protocole
  aujourd'hui).
- Un pont peut être partagé par plusieurs `I2C` (plusieurs adresses sur un même bus).
  La file de commandes du `BridgeEngine` sérialise tout, pas de verrou à gérer.
- **Un Protocol est possible sous le pont** (ex. carte custom en ASCII délimité par
  `\n`). Il faut pour cela ajouter à `ProtocolEngine` un `PayloadSink`, équivalent de
  `FrameSink`, et une interface commune aux deux engines (écriture sans attente, sink,
  deadline, auto-open). Le pont est générique sur le type de la couche du dessous :
  `SPIBridge[str]`, `I2CBridge[bytes]`…
- GPIO : reste dans le driver/pont spécifique au chip, pas d'adapter dédié.

### Pile complète

```
Driver du capteur            bloquant, toujours au sommet
 └ Protocol (optionnel)      ex. Registers
    └ I2C / SPI              Adapter de bus
       └ Bridge              générateurs, non bloquant (ou natif)
          └ Protocol (opt.)  ex. Delimited, Modbus
             └ Adapter       SerialPort, HID, IP…
```

### Exemples d'API visés

```python
# Carte sur mesure : commandes ASCII sur port série
class MaCarte(SPIBridge[str]):
    def spi_transfer(self, data, cs):
        resp = yield f"SPI {cs} {data.hex()}"   # Delimited ajoute le \n
        return bytes.fromhex(resp)

spi = SPI(MaCarte(Delimited(SerialPort("/dev/ttyUSB0", 115200))), cs=0)
spi.transfer(b"\x9f\x00\x00\x00")

# MCP2221 (I2C + GPIO via HID)
class MCP2221(I2CBridge[bytes]):
    def i2c_write_read(self, address, data, n):
        yield self._cmd(0x94, address, data)     # écriture sans STOP
        yield self._cmd(0x93, address, n)        # lecture avec repeated start
        while True:
            resp = yield self._cmd(0x40)         # récupérer les données
            if resp[1] == 0x00:
                return resp[4:4 + n]

mcp = MCP2221(HID("04d8:00dd"))
capteur = I2C(mcp, address=0x48)
eeprom = I2C(mcp, address=0x50)
mcp.gpio_set(0, True)

# I2C natif (Linux : carte mère, Raspberry Pi)
I2C(LinuxI2C("/dev/i2c-1"), address=0x48)
I2C("/dev/i2c-1", address=0x48)                 # raccourci par chaîne
```

API utilisateur : `I2C.write()`, `read(n)`, `write_read(data, n)` ; `SPI.transfer()`.
En interne, l'engine manipule des transactions (`DataT` n'est pas `bytes`, comme
`IPServer` avec `DataT = IP`), donc SCPI, Delimited et Raw ne se posent pas sur
`I2C`/`SPI`.

## Points ouverts

- **Ponts natifs et reactor** : l'ioctl bloque le reactor pendant toute la transaction
  (une EEPROM de 4 ko à 100 kHz ≈ 400 ms). Options : découper les transferts, ou
  exécuter les ponts natifs dans un pool de threads partagé (préférence pour le pool).
  À trancher à l'étape 4.
- Sémantique des timeouts entre le bus et les couches du dessous (le timeout du bus
  couvre la transaction complète).
- Pas d'accès I²C/SPI natif générique sous Windows/macOS : pont obligatoire.

## Plan

1. **`HID`** : reports bruts, `FragmentSC`, feature reports, `report_id`,
   `list_usb_devices()`, extra `syndesi[hid]`, intégration `auto.py`, CLI, UI, tests.
2. **Interface commune** `AdapterEngine` / `ProtocolEngine`, `PayloadSink`, puis
   **`BridgeEngine`** (ponts générateurs et natifs).
3. **`I2C`, `SPI`**, `I2CBridge`, `SPIBridge`, puis `MCP2221` et la carte sur mesure en
   exemple dans `examples/`.
4. **`LinuxI2C`, `LinuxSPI`**, raccourci par chaîne.
5. Plus tard : adapter **USB** brut (pyusb), à visée pédagogique. Attention à la
   friction sous Windows (WinUSB via Zadig).
