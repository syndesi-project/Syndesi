# Syndesi — Analyse d'architecture et proposition

*Analyse de la branche `codegen` — 7 septembre 2026*

---

## Table des matières

1. [La cause racine](#1-la-cause-racine)
2. [Les défauts constatés](#2-les-défauts-constatés)
3. [Faut-il tout écrire en async ?](#3-faut-il-tout-écrire-en-async-)
4. [L'architecture proposée](#4-larchitecture-proposée)
5. [Les décisions tranchées](#5-les-décisions-tranchées)
6. [Ce qui disparaît](#6-ce-qui-disparaît)
7. [Ordre de construction](#7-ordre-de-construction)

---

## 1. La cause racine

Syndesi a **deux axes de variation** :

- **quel transport** — IP, SerialPort, Visa, IPServer (beaucoup, et il y en aura d'autres)
- **comment on attend** — sync, async (deux, et il n'y en aura jamais trois)

Aujourd'hui, les deux sont exprimés **par héritage**. Deux axes d'héritage qui se croisent produisent un diamant **par construction** :

```
                    ComponentCommon
                   /               \
        AdapterCommon           Component / AsyncComponent
              |                        |
          _IPCommon              BytesAdapter / AsyncBytesAdapter
                   \               /
                    IP  /  AsyncIP
```

Ce n'est pas un accident d'implémentation qu'on pourrait ranger plus proprement : c'est la forme obligatoire dès qu'on choisit ce schéma. Le `XCommon` ajouté à chaque étage (`ComponentCommon`, `AdapterCommon`, `_IPCommon`, `ProtocolCommon`, `ModbusCommon`) est le **symptôme**, pas la solution — c'est le sommet du diamant qu'on essaie de rendre inoffensif.

Or, quand on regarde le code, **sync et async ne sont pas deux implémentations**. Tout se passe dans le thread `AdapterWorker`, piloté par `select()`. Chaque opération utilisateur est soumise comme un `ThreadCommand` (un `concurrent.futures.Future`). La seule différence entre les deux mondes :

```python
future.result(timeout)              # sync
await asyncio.wrap_future(future)   # async
```

**Une ligne.** Cette ligne est aujourd'hui propagée à travers 7 familles de classes, 3 niveaux d'héritage, et deux transpileurs AST de 530 lignes.

---

## 2. Les défauts constatés

### 2.1 Le diamant avale silencieusement les implémentations

```
$ python -c "from syndesi import IP; IP('127.0.0.1', 9999)"
TypeError: Can't instantiate abstract class IP with abstract methods
           clear_event_callbacks, is_open, register_event_callback
```

Ces trois méthodes **sont** implémentées, sur `AdapterWorkerInterface`. Mais le MRO les rend invisibles :

```
IP → _IPCommon → BytesAdapter → Adapter → AdapterCommon
   → Component → ComponentCommon → ABC → AdapterWorkerInterface
                 ^^^^^^^^^^^^^^^         ^^^^^^^^^^^^^^^^^^^^^^
                 déclare abstrait        implémente
```

`ComponentCommon` précède `AdapterWorkerInterface`, donc `getattr(IP, 'is_open')` trouve la version abstraite et Python considère la classe incomplète.

État actuel des classes principales :

| Classe | Méthodes abstraites résiduelles |
|---|---|
| `Protocol`, `Delimited`, `Raw`, `SCPI` | `is_open`, `query_detailed` |
| `AsyncProtocol`, `AsyncDelimited`, `AsyncRaw` | `close_async`, `open` |
| `IP`, `SerialPort`, `Visa` | `is_open`, `register_event_callback`, `clear_event_callbacks` |

`Protocol` n'ayant pas `query_detailed`, `SCPIDriver.get_identification()` (qui appelle `self._prot.query(...)`) est cassé lui aussi.

> **Le point important** : l'ordre du MRO est devenu une contrainte invisible que rien ne vérifie. Sur `main`, `class IP(BytesAdapter)` en héritage simple ne pose aucun problème. Le diamant est arrivé avec l'async.

### 2.2 L'ordre de construction est un contrat caché

`syndesi/adapters/ip.py:222-236` :

```python
_IPCommon.__init__(self, ...)      # doit venir en premier
BytesAdapter.__init__(self, ...)   # lit self.default_timeout, fourni par _IPCommon
```

Aucun `super()` coopératif, aucun moyen de forcer l'ordre. On inverse les deux lignes → `AttributeError` levée depuis un thread worker. Ce contrat n'est écrit nulle part.

### 2.3 `super()` dans un mixin n'a pas de sens défini

`syndesi/adapters/ip.py:163` — `_IPCommon._worker_close()` appelle `super()._worker_close()`. Le MRO propre de `_IPCommon` ne contient aucun `_worker_close` : ça ne fonctionne que grâce à ce que `IP` hérite *par ailleurs*.

Et `_SerialPortCommon` (`serialport.py:88`) ne déclare même pas de base, alors que `_IPCommon` hérite de `AdapterCommon[bytes]` — deux formes différentes du même motif.

### 2.4 Le thread worker démarre sur un objet à moitié construit

`AdapterWorker.__init__` fait `self._worker_thread.start()` (`adapterworker.py:422`). Il est instancié dans `BytesAdapter.__init__` via `BytesAdapterWorker(self)`, **avant** que `AdapterWorkerInterface.__init__` n'ait posé `_alias`, `_worker`, `_event_callbacks`. La boucle appelle immédiatement `self._interface._selectable()`.

### 2.5 De la duplication qui ne contient aucun async

Mesuré par comparaison AST, après avoir retiré `async` / `await` / le préfixe `Async` :

| Paire | Lignes | Identique |
|---|---|---|
| `BytesAdapter` / `AsyncBytesAdapter` | 90 / 91 | **99 %** |
| `IP` / `AsyncIP` | 71 / 71 | **100 %** |
| `SerialPort` / `AsyncSerialPort` | 55 / 48 | 91 % |
| `Component` / `AsyncComponent` | 72 / 78 | 90 % |
| `Protocol` / `AsyncProtocol` | 95 / 108 | 69 % |
| `Adapter` / `AsyncAdapter` | 90 / 86 | 60 % |
| `Modbus` / `AsyncModbus` | 958 / 779 | 58 % |

`AsyncBytesAdapter` est une copie littérale : `set_stop_conditions`, `stop_conditions`, `set_default_stop_conditions` — **aucune n'est une coroutine**. 90 lignes dupliquées pour zéro différence.

### 2.6 La dérive est déjà là — et les pourcentages bas la mesurent

Les paires les plus dupliquées sont à 99–100 %. Celles à 58–69 % ne sont pas « moins dupliquées », elles ont **divergé** :

- `AsyncModbus` n'a ni `__init__`, ni `default_timeout`, ni `_protocol_to_adapter`, ni `_adapter_to_protocol` — donc les 4 méthodes abstraites.
- 3 méthodes sur 36 y sont nommées `aread_coils`, `amask_write_register`, `aread_fifo_queue` ; les 33 autres portent le nom nu. **Deux conventions dans la même classe.**
- `AsyncProtocol` définit `close()` alors que `AsyncComponent` déclare `close_async()`.
- `Protocol` (sync) n'a jamais reçu `query_detailed` ; `AsyncProtocol` l'a.
- `AsyncDelimited` et `AsyncRaw` sont littéralement `...`.

### 2.7 Deux bugs qui découlent directement du découpage

- `ip.py:100` — dans `_IPCommon.__init__`, `auto_open = False` est une **variable locale morte**. L'intention (désactiver l'auto-open pour un socket serveur) est perdue parce que `auto_open` vit dans l'autre branche du diamant.
- `adapter.py:227` — `AsyncAdapter.__init__` appelle `self.open()`, la version **bloquante**, et `AsyncIP` passe `auto_open=True` par défaut.

*(Hors architecture, mais lié au cycle adapter ↔ worker : `weakref.finalize(self, self._cleanup)` en `adapter.py:57` — la méthode liée garde une référence forte sur `self`, donc le finalizer ne peut jamais se déclencher avant la fin de l'interpréteur.)*

### 2.8 Les générateurs sont le symptôme, pas le remède

530 lignes de transpileurs AST dont les docstrings avouent elles-mêmes les limites :

> *« Not a general transpiler »*
> *« those get rule C […] left sync, unawaited »*
> *« still gets converted, just imperfectly — don't mark it either »*

La complexité n'est pas supprimée, elle est déplacée dans un outil qui doit deviner.

---

## 3. Faut-il tout écrire en async ?

L'idée « écris tout en async, génère le sync » recouvre deux propositions très différentes.

### Variante A — le worker reste, on écrit en async par-dessus

Ne fonctionne pas. Le worker rend des `Future`. Une façade async par-dessus, c'est `await wrap_future(f)`. Mais alors comment fabriquer le sync ? Il faudrait *dé-awaiter*, donc lancer une boucle d'événements juste pour ré-obtenir ce que `f.result()` donnait gratuitement. On aurait ajouté une boucle d'événements pour retrouver le point de départ.

### Variante B — le worker disparaît, remplacé par asyncio

Architecture cohérente et réelle (pattern « portal » : une boucle dans un thread dédié + `run_coroutine_threadsafe(coro, loop).result()`). C'est la question sérieuse.

**Ce qu'elle gagnerait :** ~300 lignes de réacteur `select()` en moins, l'annulation propre (`task.cancel()`), DNS non bloquant / TLS / happy-eyeballs gratuits pour IP, intégration naturelle avec l'UI dearpygui async.

**Ce qu'elle coûte, vérifié dans le code :**

- **Le thread ne disparaît pas.** `visa.py:143-286` lance déjà son propre thread + `queue` + `socketpair` pour devenir sélectionnable, parce que pyvisa est bloquant et n'a pas de fd. Ça reste vrai avec asyncio.
- **Serial sur Windows non plus.** `_selectable()` renvoie `self._port` (`serialport.py:224`) ; `serial.Serial.fileno()` n'existe pas sous Win32. Et asyncio ne sait pas faire mieux : `ProactorEventLoop` n'a pas `add_reader`, `SelectorEventLoop` sous Windows ne gère que des sockets. → thread dédié obligatoire, dans les deux architectures.
- **Les utilisateurs sync paient une boucle dans un thread.** Le thread d'arrière-plan n'est pas supprimé, il est déplacé — et rendu obligatoire même pour un `IP(...).query(...)` en script.
- **La partie d'asyncio qui ferait envie est justement celle qu'on ne peut pas utiliser.** `open_connection` / `StreamReader` / `data_received` retirent le contrôle du moment exact du `recv()` et du timestamp — or c'est toute la valeur ajoutée de Syndesi (fragments horodatés, `Continuation`, `Total`). Il faudrait donc rester au niveau `loop.add_reader` + son propre `recv()` : un réacteur, remplacé par un réacteur.

### Le point de fond : l'asymétrie du coût de traduction

| cœur | → façade sync | → façade async |
|---|---|---|
| bloquant | **gratuite** | thread pool par appel |
| asyncio | boucle dans un thread + `run_coroutine_threadsafe` | **gratuite** |
| **`Future`** | `.result()` — **gratuite** | `wrap_future()` — **gratuite** |

Le `Future` est le **seul point neutre des trois**. « Tout écrire en async » revient à *colorer* un cœur qui peut rester incolore, puis à payer la décoloration pour la moitié des utilisateurs.

### Verdict par couche

| couche | forme canonique | pourquoi |
|---|---|---|
| Backend | **bloquante, nue** | c'est `socket.recv()`, sans plus |
| Engine | **`Future`** | seul point neutre, façades gratuites des deux côtés |
| Façades | 2 classes, ~60 lignes | le seul endroit où sync ≠ async |
| Commandes (Modbus, drivers) | **async, sync généré** | 40× le même geste, transformation sûre |

Pour la dernière ligne, l'argument est déjà écrit dans `scripts/gen_sync.py` :

> *« this is the safer direction: removing concurrency ceremony (await/async) cannot introduce a wrong scheduling decision the way inserting it can »*

C'est exact — et c'est pour ça que `gen_sync.py` peut se permettre d'être strict et autonome pendant que `gen_async.py` doit deviner.

---

## 4. L'architecture proposée

### Le principe, dérivé des contraintes

| Contrainte (vérifiée dans le code) | Ce qu'elle impose |
|---|---|
| Horodatage des fragments au plus près du syscall | contrôle du `recv()` → réacteur bas niveau |
| Stop-conditions à échéances (`Continuation`, `Total`) | réacteur avec deadlines |
| Visa bloquant, Serial-Windows sans `fileno()` | **un thread est obligatoire de toute façon** |
| Utilisateurs sync sans boucle d'événements | le sync ne doit rien coûter |
| UI async + `asyncio.gather` | l'async ne doit rien coûter |

> **Le cœur ne connaît ni `sync` ni `async`. Il est écrit une fois. Les deux façades sont deux fichiers de délégation sans logique.**

### Vue d'ensemble — 5 couches, 3 natures

```
┌──────────────────────────────────────────────────────────────┐
│  syndesi/            │  syndesi/aio/         ← 2 façades      │
│  IP · Delimited      │  IP · Delimited          (délégation)  │
│  .result()           │  await wrap_future()                   │
├──────────────────────┴───────────────────────────────────────┤
│  Engine[T]              → Future                 ← écrit 1×   │
│  ouvre/lit/écrit, expose des Future, ne bloque jamais         │
├───────────────────────────────────────────────────────────────┤
│  Reactor                → 1 thread pour tout le process       │
│  un select() sur tous les backends + un tas d'échéances       │
├───────────────────────────────────────────────────────────────┤
│  Framer[T] · Codec[A,B] → PUR, sans I/O, sans thread          │
│  fragments+timestamps → frames  ·  frames → payloads          │
├───────────────────────────────────────────────────────────────┤
│  Backend[T]             → bloquant, nu, aucune classe de base │
│  IPBackend · SerialPortBackend · VisaBackend                  │
└───────────────────────────────────────────────────────────────┘
```

Trois natures, jamais mélangées : **pur** (Framer, Codec), **bloquant nu** (Backend), **`Future`** (Engine). L'async n'existe qu'à l'étage du haut.

### `Backend` — le dialogue matériel, et rien d'autre

Un `typing.Protocol` structurel. **Aucune classe de base, donc aucun `super()`, aucun MRO, aucun diamant possible.**

```python
class Backend(Protocol[T]):
    descriptor: Descriptor
    default_timeout: float | None
    def open(self) -> None: ...
    def close(self) -> None: ...
    def read_fragment(self, timestamp: float) -> Fragment[T]: ...
    def write(self, data: T) -> None: ...
    def selectable(self) -> HasFileno | None: ...
```

`IPBackend` ≈ 80 lignes. Testable sans lancer un thread.

Un backend non pollable (Visa, Serial-Windows) lance son propre thread lecteur et renvoie un `socketpair` depuis `selectable()` — c'est déjà exactement ce que fait `visa.py:143`, et c'est la bonne réponse générique.

### `Framer` / `Codec` — sans-io, la partie qu'il faut pouvoir tester à froid

```python
class Framer(Protocol[T]):
    def push(self, fragment: Fragment[T]) -> list[ReadFrame[T]]: ...
    def next_deadline(self) -> float | None: ...
    def on_deadline(self, now: float) -> list[ReadFrame[T]]: ...
    def reset(self) -> None: ...

class Codec(Protocol[WireT, FrameT]):
    default_timeout: float | None
    def decode(self, frame: ReadFrame[WireT]) -> FrameT: ...
    def encode(self, payload: FrameT) -> WireT: ...
    def stop_conditions(self) -> list[StopCondition] | None: ...
```

Toute la logique de stop-conditions devient une fonction pure de `(fragments, timestamps)`. On la teste en lui injectant des octets et des horodatages : sans socket, sans thread, sans attente.

C'est aujourd'hui la partie la plus subtile de Syndesi et la plus difficile à tester — elle devient la plus facile.

`BytesFramer` porte les stop-conditions ; `IPServer[Client]` prend un framer trivial. `Delimited`, `Raw`, `SCPI` deviennent des `Codec`.

### `Reactor` — un seul thread pour tout le processus

C'est le changement que le code actuel ne fait pas et qui vaut le coup : aujourd'hui c'est un thread + un socketpair **par adapter**.

```python
class Reactor:
    def attach(self, engine) -> None: ...
    def detach(self, engine) -> None: ...
    def submit(self, engine, command) -> None: ...   # enfile + réveille
```

Un `select()` sur tous les backends, un tas d'échéances fusionné, un socketpair. 20 instruments = 1 thread.

Bénéfices de bord :

- les horodatages deviennent **comparables entre adapters** (utile pour tracehub)
- `IPServer` qui fabrique des adapters clients devient naturel : ils s'attachent au même réacteur

*Règle :* les callbacks sont dispatchés sur le thread réacteur et doivent être non bloquants — comme aujourd'hui, mais c'est maintenant une contrainte explicite. Prévoir un `Reactor()` dédié en option pour isoler un adapter capricieux.

### `Engine[T]` — la couche neutre, écrite une seule fois

Pas de thread à lui, pas de sync, pas d'async. Il enfile des commandes et rend des `Future`.

```python
class Engine(Generic[T]):
    def __init__(self, backend: Backend[T], framer: Framer[T], *,
                 timeout, alias, reactor: Reactor | None = None) -> None: ...

    def open(self)  -> Future[None]: ...
    def close(self) -> Future[None]: ...
    def read(self, *, timeout, scope, stop_conditions) -> Future[ReadFrame[T]]: ...
    def write(self, data: T) -> Future[None]: ...
    def clear(self) -> Future[None]: ...
```

Le backend est entièrement construit **avant** que l'engine n'existe, et l'engine avant l'attachement au réacteur. Le défaut 2.4 (objet à moitié construit vu par le thread) disparaît structurellement.

### Les deux façades — le seul endroit du projet où sync ≠ async

```python
# syndesi/_endpoint.py                     # syndesi/aio/_endpoint.py

class Endpoint(Generic[T]):                class Endpoint(Generic[T]):
    def open(self) -> None:                    async def open(self) -> None:
        self._e.open().result(T_OPEN)              await wrap_future(self._e.open())

    def read(self, **kw) -> T:                 async def read(self, **kw) -> T:
        return self._e.read(**kw)                  f = self._e.read(**kw)
                   .result(None).data              return (await wrap_future(f)).data
```

≈ 60 lignes chacune. **Jamais sous-classées pour ajouter un transport.**

Puis un **arbre** — pas un diamant, parce qu'il n'y a plus de double héritage nulle part :

```
Endpoint ─┬─ Adapter ── IP · SerialPort · Visa · IPServer
          └─ Protocol ─ Delimited · Raw · SCPI · Modbus
```

Et la même chose, en miroir, sous `syndesi/aio/`. **Les deux arbres ne se touchent jamais** : ce qu'ils partagent (`IPBackend`, `BytesFramer`, `DelimitedCodec`, `Engine`) est *composé*, pas hérité.

> C'est le cœur de la proposition : **l'axe qui varie beaucoup (transport) passe en composition ; l'axe qui varie deux fois (sync/async) reste en héritage.** Un seul axe d'héritage ⇒ pas de diamant, mathématiquement.

---

## 5. Les décisions tranchées

### 5.1 `syndesi.aio`, pas `AsyncXxx`

```python
from syndesi import IP, Delimited            # sync
from syndesi.aio import IP, Delimited        # async — noms identiques
```

C'est ce que font psycopg et redis-py. Ça supprime **100 %** de la dérive de nommage déjà constatée en 2.6 (`aread_coils` à côté de `read_coils` dans la même classe).

Sur la façade async, les méthodes portent leur nom nu — `open`, pas `open_async` : le type dit déjà tout.

*Compromis :* mixer les deux dans un même fichier demande `from syndesi import aio` puis `aio.IP(...)`. Acceptable.

### 5.2 Un transport = un constructeur de 6 lignes, écrit deux fois

```python
# syndesi/adapters/ip.py                    # syndesi/aio/adapters/ip.py

class IP(Adapter[bytes]):                   class IP(Adapter[bytes]):
    def __init__(self, address, port=None,      def __init__(self, address, port=None,
                 transport='TCP', **kw):                      transport='TCP', **kw):
        super().__init__(                           super().__init__(
            IPBackend(address, port,                    IPBackend(address, port,
                      transport),                                 transport),
            BytesFramer(), **kw)                        BytesFramer(), **kw)
```

Oui, c'est dupliqué — **volontairement**. Garder de vraies classes préserve l'autocomplétion, la docstring, `isinstance`, la signature : ça compte énormément pour une bibliothèque utilisateur. Et ces lignes ne contiennent **aucune logique**, donc elles ne peuvent pas diverger sémantiquement.

La documentation des paramètres vit sur le backend ; les docstrings de classe restent courtes.

### 5.3 `open()` dans `__init__` : `async with` + soumission sans attente

```python
adapter = IP('192.168.1.10', 5025)              # sync : auto_open bloquant, comme avant

async with IP('192.168.1.10', 5025) as adapter: # async : idiome principal
    await adapter.query(b'*IDN?\n')
```

Et pour que `auto_open=True` fonctionne aussi côté async sans bloquer : `__init__` **poste** `OpenCommand` sans appeler `.result()`.

C'est sûr — la queue de commandes est FIFO et `_worker_manage_command` les traite strictement dans l'ordre — donc l'`OpenCommand` postée à la construction est forcément traitée avant tout `ReadCommand` ultérieur. La première lecture s'aligne naturellement derrière l'ouverture. Pas de boucle d'événements requise à la construction.

> C'est un cadeau du cœur `Future` : avec un cœur asyncio ce serait impossible — il faudrait un `loop.create_task`, et il n'y a pas forcément de boucle au moment du `__init__`.

Les erreurs d'ouverture remontent au premier usage, ou plus tôt via un `await adapter.opened` explicite.

### 5.4 Les événements deviennent des itérateurs

```python
for event in adapter.events(): ...          # queue.Queue
async for event in adapter.events(): ...    # asyncio.Queue via call_soon_threadsafe
```

Même forme des deux côtés, et c'est le bon pont vers l'UI dearpygui. Les callbacks restent disponibles pour tracehub.

### 5.5 Modbus : les commandes deviennent des données

```python
def read_holding_registers(start: int, count: int) -> Command[list[int]]:
    return Command(
        ReadHoldingRegisters(start_address=start, number_of_registers=count),
        lambda r: cast(ReadHoldingRegisters.Response, r).registers,
    )
```

Écrit **une fois**, ni sync ni async. Les façades n'ont qu'une seule méthode générique, parfaitement typée sans acrobatie :

```python
def run(self, cmd: Command[R]) -> R: ...           # sync
async def run(self, cmd: Command[R]) -> R: ...     # async
```

Puis les 40 méthodes de confort (`modbus.read_holding_registers(0, 10)`) sont **générées** depuis la table des commandes. Le générateur ne produit plus que des signatures, jamais de corps : ~60 lignes, zéro sémantique à deviner, dérive impossible.

Bénéfice de bord : une commande est un objet — donc loggable, rejouable, testable sans appareil, et batchable (`run_many`) plus tard.

### 5.6 Les drivers utilisateurs n'héritent pas du fardeau

Un auteur de driver écrit **la version dont il a besoin**. 99 % du temps c'est sync, et il ne pense jamais à l'async. S'il veut les deux, il écrit en async et lance `gen_sync.py`.

C'est le seul usage légitime restant d'un générateur.

---

## 6. Ce qui disparaît

| Aujourd'hui | Devient |
|---|---|
| `ComponentCommon` · `Component` · `AsyncComponent` | rien (protocoles structurels si besoin) |
| `AdapterCommon` · `AdapterWorkerInterface` | `Backend` (device) + `Engine` (commandes) |
| `_IPCommon` · `_SerialPortCommon` | `IPBackend` · `SerialPortBackend` |
| `BytesAdapter` + `AsyncBytesAdapter` (99 % identiques) | `BytesFramer`, pur |
| `ProtocolCommon` · `ModbusCommon` | `ProtocolEngine` + `Codec` |
| `AdapterWorker` + `BytesAdapterWorker` | `Reactor` (1 thread) + `Framer` composé |
| `gen_async.py` (209 lignes) | supprimé |
| `gen_sync.py` (323 lignes) | outil optionnel pour auteurs de drivers |
| 1 thread **par adapter** | 1 thread par **processus** |

Duplication sync/async restante dans toute la bibliothèque : **≈ 130 lignes** de délégation sans logique, contre ~900 aujourd'hui. Et aucune ne peut diverger sémantiquement.

Défauts du §2 réglés structurellement : 2.1 (plus de diamant), 2.2 (un seul `__init__`), 2.3 (plus de mixin à `super()`), 2.4 (construction ordonnée), 2.5 et 2.6 (plus rien à dupliquer), 2.7 (un seul endroit où vit `auto_open`), 2.8 (`gen_async.py` supprimé).

---

## 7. Ordre de construction

Chaque étape est testable seule, et les trois premières ne touchent à rien d'async.

1. **`Framer` + `Codec` en pur** — extraire la logique stop-conditions et l'encodage. Tests sans I/O.
   *C'est le socle, et la partie la plus risquée à porter : commencer par là pendant que l'ancien code sert encore d'oracle.*
2. **`Backend`** — déplacement quasi littéral de `_IPCommon`, `_SerialPortCommon`, du device-code de `Visa`.
3. **`Reactor` + `Engine`** — le thread unique et l'API `Future`. À ce stade tout peut déjà tourner en sync via `.result()` direct, sans façade.
4. **Façade sync** (`syndesi/`) — l'API publique actuelle revient à l'identique.
5. **Façade async** (`syndesi/aio/`) — miroir, ~80 lignes. C'est le moment où l'async cesse d'être un problème.
6. **Modbus** — commandes en données + génération des méthodes de confort.

Le point de bascule est l'étape 1 : dès que `Framer` est pur et testé, le reste est de l'assemblage.
