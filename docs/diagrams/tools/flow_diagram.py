from graphviz import Digraph

from .diagram import PolygonNode
from .styling import Presets


class Start(PolygonNode):
    def __init__(self, name: str = "Start") -> None:
        super().__init__(name)

    def _render(self, graph: Digraph):
        graph.node(
            self.id, self.name, shape="box", style="rounded,filled", **Presets.node
        )


class End(Start):
    def __init__(self, name: str = "End") -> None:
        super().__init__(name)


class InputOutput(PolygonNode):
    def __init__(self, name: str = "Start") -> None:
        super().__init__(name)

    def _render(self, graph: Digraph):
        graph.node(
            self.id,
            self.name,
            **Presets.node,
            shape="polygon",
            style="filled",
            sides="4",  # four sides
            skew="0.2",  # slant the shape
        )


class Decision(PolygonNode):
    def __init__(self, name: str = "Decision") -> None:
        super().__init__(name)

    def _render(self, graph: Digraph):
        graph.node(self.id, self.name, **Presets.node, shape="diamond", style="filled")


class Process(PolygonNode):
    def __init__(self, name: str = "Process") -> None:
        super().__init__(name)

    def _render(self, graph: Digraph):
        graph.node(self.id, self.name, **Presets.node, style="filled", shape="box")
