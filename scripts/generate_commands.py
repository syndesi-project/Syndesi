"""
@Author: Sébastien Deriaz
@Date: 06.06.2022

Commands.py script
Generate code based on the commands.yaml file
Those files contains the enums for each command of the
Syndesi project as well as the structs corresponding to each content

A template (.txt) is used for each file and keys (>>>...<<<) are replaced by their corresponding content
"""

import yaml
from datetime import datetime
from os.path import join, dirname, exists
from pathlib import Path    
from utilities import replace, replace_str
from commands import Command
from settings import YAML_ALIAS_KEY, YAML_COMMANDS_LIST_KEY, YAML_SETTINGS_KEY
from cpp import CPP
from md import MD
import re

# Other repositories
repos_path = {
    "documentation" : join(dirname(__file__), "../../documentation")
}

for p in repos_path.values():
    # Check if the repo exists and if there's a .git file
    assert exists(join(p, ".git")), f"Repository {p} doesn't exist"




# Files
COMMANDS_DESCRIPTION_FILE = join(dirname(__file__), "commands.yaml")

# Each of the following file is a tuple (template, output)
# C++
PAYLOADS_H = (join(dirname(__file__), "payloads_template.h.txt"),join(dirname(__file__), "../include/payloads.h"))
PAYLOADS_CPP = (join(dirname(__file__), "payloads_template.cpp.txt"), join(dirname(__file__), "../src/payloads.cpp"))
CONFIG_H = (join(dirname(__file__), "syndesi_config_template.h.txt"), join(dirname(__file__), "../user_config/syndesi_config.h"))
CALLBACKS_H = (join(dirname(__file__), "callbacks_template.h.txt"), join(dirname(__file__), "../include/callbacks.h"))
FRAME_MANAGER_CALLBACKS_CPP = (join(dirname(__file__), "framemanagercallbacks_template.cpp.txt"), join(dirname(__file__), "../src/framemanagercallbacks.cpp"))

# Python
COMMANDS_PY = (join(dirname(__file__), "payloads_template.py"), join(dirname(__file__), "../Python/syndesi/syndesi/payloads.py"))

# Markdown
COMMANDS_LIST_MD = (join(dirname(__file__), "commands_list_template.md"), join(dirname(__file__), join(repos_path["documentation"], "communication/commands_list.md")))

def main():
    # Read the description file
    with open(COMMANDS_DESCRIPTION_FILE, 'r', encoding='utf-8') as desc:
        desc_content = yaml.full_load(desc)
        # Load commands
        commands = [Command(cmd) for cmd in desc_content[YAML_COMMANDS_LIST_KEY]]
        # Load special values

        settings = desc_content[YAML_SETTINGS_KEY]

        cpp = CPP(commands)
        md = MD(commands)
        # Create C++ header
        replace(*PAYLOADS_H, {
            "date" : datetime.strftime(datetime.now(), "%y-%m-%d %H:%M:%S"),
            "file" : Path(__file__).name,
            "commands" : cpp.commands_enum(),
            "payloads" : cpp.payloads()
        })
        # Create C++ source
        replace(*PAYLOADS_CPP, {
            "date" : datetime.strftime(datetime.now(), "%y-%m-%d %H:%M:%S"),
            "file" : Path(__file__).name,
            "commands_names_switch" : cpp.commands_names_switch(),
            "commands_ids" : cpp.commands_ids()
        })

        # Create C++ callbacks configuration file (for the user to edit)
        replace(*CONFIG_H, {
            "date" : datetime.strftime(datetime.now(), "%y-%m-%d %H:%M:%S"),
            "file" : Path(__file__).name,
            "request" : cpp.defines(request=True),
            "reply" : cpp.defines(request=False)
        })

        

        # Create C++ callbacks source file
        replace(*FRAME_MANAGER_CALLBACKS_CPP, {
            "date" : datetime.strftime(datetime.now(), "%y-%m-%d %H:%M:%S"),
            "file" : Path(__file__).name,
            "switch_request" : cpp.switch(request=True),
            "switch_reply" : cpp.switch(request=False)
        })

        # Create C++ callbacks header file
        replace(*CALLBACKS_H, {
            "date" : datetime.strftime(datetime.now(), "%y-%m-%d %H:%M:%S"),
            "file" : Path(__file__).name,
            "callbacks" : cpp.callbacks()
        })

        replace(*COMMANDS_LIST_MD, {
            "date" : datetime.strftime(datetime.now(), "%y-%m-%d %H:%M:%S"),
            "file" : Path(__file__).name,
            "list" : md.commands_list()
        })

        


        # # Create Python module
        # replace(COMMANDS_PY_TEMPLATE_FILE, COMMANDS_PY_OUTPUT_FILE, {
        #     "date" : datetime.strftime(datetime.now(), "%y-%m-%d %H:%M:%S"),
        #     "file" : Path(__file__).name,
        #     "commands" : commands.python_commands(),
        #     "payloads" : commands.python_contents(),
        #     "special_values" : special_values.python(),
        #     "endian" : f"FRAME_ENDIAN = \"{FRAME_ENDIAN}\"",
        #     "payload_match" : commands.python_frames_match()
        # })

if __name__ == '__main__':
    main()
