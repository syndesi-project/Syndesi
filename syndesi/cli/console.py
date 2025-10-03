# File : console.py
# Author : Sébastien Deriaz
# License : GPL

import asyncio
import os
import sys
from collections.abc import Callable
from enum import Enum
from pathlib import Path

import prompt_toolkit
from platformdirs import user_data_dir
from prompt_toolkit import PromptSession
from prompt_toolkit.application import get_app
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import FuzzyCompleter, WordCompleter
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.keys import Keys

from ..version import AUTHOR, NAME


class Shell:
    class Style(Enum):
        DEFAULT = ""
        HIGHLIGHT = "highlight"
        NOTE = "note"
        WARNING = "warning"
        _PROMPT = "prompt-marker"
        _REVERSE_SEARCH_SELECTION = "rss"
        _REVERSE_SEARCH = "rs"
        _REVERSE_SEARCH_LINE = "rs-line"
        ERROR = "error"

    HISTORY_SIZE = 10

    STYLES = {
        "highlight": "bg:#444444 #ffffff",  # background gray, foreground white
        "prompt-marker": "bold #146DA8",  # bright green marker
        "rss": "bold bg:#505050",
        "rs": "",
        Style._REVERSE_SEARCH_LINE.value: "bold bg:#505050 #ff5010",
        Style.DEFAULT.value: "",
        Style.NOTE.value: "#A0A0A0",
        Style.WARNING.value: "#ba9109",
        Style.ERROR.value: "#8f2d2d",
    }

    _toolkit_styles = prompt_toolkit.styles.Style.from_dict(STYLES)

    RS_CAPTURE_KEY = ["<any>", "up", "down", "enter"]

    DEFAULT_PROMPT = prompt_toolkit.formatted_text.FormattedText(
        [("class:" + Style._PROMPT.value, "❯ ")]
    )

    def __init__(
        self,
        on_command: Callable[[str], None],
        history_file_name: str,
        commands: list[str] | None = None,
    ):
        # Get the appropriate directory
        data_dir = Path(user_data_dir(NAME, AUTHOR))
        data_dir.mkdir(parents=True, exist_ok=True)

        # Now you can store your history file here
        history_file = data_dir / history_file_name

        self.on_command = on_command
        self._history: FileHistory = FileHistory(str(history_file))

        word_completer = WordCompleter([] if commands is None else commands)

        self.update_reverse_search_entries()
        self.session: PromptSession[str] = prompt_toolkit.PromptSession(
            history=self._history,
            auto_suggest=AutoSuggestFromHistory(),  # enables ghost suggestions
            completer=FuzzyCompleter(word_completer),
        )
        self.kb = KeyBindings()
        self.temporary_prompt: FormattedText | None = None
        self.prompt = self.DEFAULT_PROMPT
        self.reverse_search_mode = [False]
        self.reverse_search_selection = 0
        self.ask_event = asyncio.Event()
        self.ask_callback: Callable[[str], None] | None = None

        self._stop = False

        # Find a way to have access to those variables in the event nicely

        @self.kb.add("c-r")
        def _(event: KeyPressEvent) -> None:
            self.update_reverse_search_entries()
            self.update_reverse_search()
            self.reverse_search_mode[0] = True
            for c in self.RS_CAPTURE_KEY:
                self.kb.add(c)(self.reverse_search_capture)

        self.update_reverse_search_entries()

    def update_reverse_search_entries(self) -> None:
        self._reverse_search_entries = []
        for _, x in zip(
            range(self.HISTORY_SIZE), self._history.load_history_strings(), strict=False
        ):
            self._reverse_search_entries.append(x)
        # Invert because the order is newest at the bottom
        self._reverse_search_entries = self._reverse_search_entries[::-1]
        self.reverse_search_selection = len(self._reverse_search_entries) - 1

    def update_reverse_search(self) -> None:
        entries = []
        for i, command in enumerate(self._reverse_search_entries):
            selected = i == self.reverse_search_selection
            # Add the left margin
            entries.append(("class:rs_left_line", ">" if selected else " "))
            # Space
            entries.append(("class:rss" if selected else "", " "))
            # Add the command
            entries.append(("class:rss" if selected else "", f" {command}\n"))  # Style

        self.prompt = prompt_toolkit.formatted_text.FormattedText(entries)

    def exit_reverse_search(self) -> None:
        for c in self.RS_CAPTURE_KEY:
            self.kb.remove(c)
        get_app().current_buffer.document = prompt_toolkit.document.Document(
            self._reverse_search_entries[self.reverse_search_selection]
        )
        self.prompt = self.DEFAULT_PROMPT
        self.reverse_search_mode[0] = False

    def reverse_search_capture(
        self, event: prompt_toolkit.key_binding.KeyPressEvent
    ) -> None:
        key = event.key_sequence[0].key
        exit = False
        if key == Keys.Up and self.reverse_search_selection > 0:
            self.reverse_search_selection -= 1
        elif (
            key == Keys.Down
            and self.reverse_search_selection < len(self._reverse_search_entries) - 1
        ):
            self.reverse_search_selection += 1
        elif key == Keys.Enter:
            exit = True

        if exit:
            self.exit_reverse_search()
        else:
            self.update_reverse_search()
            event.app.invalidate()

    def _get_prompt(self) -> FormattedText:
        if self.temporary_prompt is not None:
            output = self.temporary_prompt
        else:
            output = self.prompt
        return output

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        with prompt_toolkit.patch_stdout.patch_stdout():
            while not self._stop:
                try:
                    cmd = self.session.prompt(
                        self._get_prompt,  # Allows for update of the prompt
                        key_bindings=self.kb,
                        multiline=self.reverse_search_mode[0],
                        style=self._toolkit_styles,
                    )
                    if cmd is None:
                        continue

                    command = cmd.strip()

                    if self.ask_event.is_set():
                        self.ask_event.clear()
                        if self.ask_callback is not None:
                            self.ask_callback(command)
                            self.temporary_prompt = None  # Not great here but it works
                        continue

                    if command in ["clear", "cls"]:
                        if (
                            sys.platform == "linux"
                            or sys.platform == "linux2"
                            or sys.platform == "darwin"
                        ):
                            # linux
                            os.system("clear")
                        elif sys.platform == "win32":
                            # Windows
                            os.system("cls")
                        continue
                    if command in ["exit", "quit"]:
                        break

                    self.on_command(command)

                except (KeyboardInterrupt, EOFError):
                    # print_formatted_text("\nExiting.")
                    break

    def reprompt(self, text: str | None = None) -> None:
        if self.session.app.is_running:
            if text is not None:
                self.temporary_prompt = FormattedText(
                    [("class:prompt-marker", "❯ "), ("", text)]
                )
            self.session.app.invalidate()

    def print(self, text: str, style: Style = Style.DEFAULT) -> None:
        prompt_toolkit.shortcuts.print_formatted_text(
            FormattedText([(f"class:{style.value}", text)]), style=self._toolkit_styles
        )

    def ask(self, question: str, callback: Callable[[str], None]) -> None:
        self.ask_event.set()
        self.ask_callback = callback
        self.reprompt(question)