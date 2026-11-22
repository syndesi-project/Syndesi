# Examples

Short scripts, to run as they are. None needs hardware, except `serial_port.py`.

Some talk to a simulated device : start it first, in its own terminal, and leave it
running.

| Example | What it shows | Start first |
|---|---|---|
| [ip_server.py](ip_server.py) | A server and its client in one script | |
| [ip_query.py](ip_query.py) | `write`, `read` and `query` with bytes | [echo_server.py](echo_server.py) |
| [text_lines.py](text_lines.py) | Text lines with `Delimited` | [echo_server.py](echo_server.py) |
| [stop_conditions.py](stop_conditions.py) | Where a message ends : `Termination`, `Length` | [echo_server.py](echo_server.py) |
| [async_query.py](async_query.py) | The same with `async` / `await` | [echo_server.py](echo_server.py) |
| [scpi_instrument.py](scpi_instrument.py) | SCPI commands to a power supply | [drivers/fake_psu.py](drivers/fake_psu.py) |
| [scpi_driver.py](scpi_driver.py) | A driver : the instrument as a class | [drivers/fake_psu.py](drivers/fake_psu.py) |
| [modbus_client.py](modbus_client.py) | Read and write Modbus registers and coils | [modbus_device.py](modbus_device.py) |
| [serial_port.py](serial_port.py) | A device on a serial port (Arduino, ...) | a real device |

For example :

```bash
python examples/echo_server.py      # first terminal
python examples/text_lines.py       # second terminal
```

[drivers/demo_psu.py](drivers/demo_psu.py) is a richer driver (channels, a bench made of
instruments) to try in the graphical bench :

```bash
python examples/drivers/fake_psu.py
syndesi ui -l examples/drivers/demo_psu.py
```

More in the [documentation](https://syndesi.readthedocs.io/en/latest/).
