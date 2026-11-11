# File : __init__.py
# Author : Sébastien Deriaz
# License : GPL
"""
Syndesi graphical interface (PySide6), ``syndesi ui``

    app.py          main window, entry point
    worker.py       the thread every call to a component runs on
    fields.py       editors generated from the parameters of a function

    core/           the model, without Qt (tested in tests/ui/test_model.py)
      introspection   what a component is, read from its type hints and docstrings
      library         the component classes that can be stacked
      stack           the stack being edited (StackNode, Stack)
      code            the python code of a stack
      stack_file      saving and loading a stack
      runtime         what exists once built : internal layers, sub-drivers, ...

    style/          the look
      theme           design tokens, fonts, light / dark ; style.qss the stylesheet
      system          the light / dark setting of the system
      icons           line icons, redrawn when the theme changes
      widgets         small widgets shared by the screens

    stack/          first screen : assemble and configure the layers
      library_panel, canvas, inspector, screen (the controller)

    bench/          second screen : test what was built
      object_tree, io_panel, command_panel, event_log, relay (events from the reactor
      thread), screen (the controller)
"""
