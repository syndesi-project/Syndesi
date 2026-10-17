def pytest_configure(config):
    config.addinivalue_line(
        "markers", "serial_only: test runs only on serial protocols (Modbus RTU/ASCII for example)")