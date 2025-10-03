from pathlib import Path

from tools.flow_diagram import *


def main():
    g = Diagram(direction="LR")

    g.frontend = Diagram("Frontend", direction="TB")

    g.backend = Diagram("Backend", direction="TB")

    g.frontend.start = Start("User action")
    g.frontend.adapter = Process("Adapter.write")

    g.backend.adaptersession = Process("AdapterSession")

    g.backend.decision = Decision("test")

    g.frontend.test = Process("test")

    g.connect_multiple(
        [
            [
                g.frontend.adapter,
                g.backend.adaptersession,
                "(Action.Write, data)",
                ConnectStyle.FRONTEND_BACKEND,
            ],
            [g.frontend.start, g.frontend.adapter],
            [g.frontend.test, g.frontend.start],
            [g.backend.adaptersession, g.frontend.test],
        ]
    )

    g.render(Path(__file__).parent / "write", view=False)


if __name__ == "__main__":
    main()
