import os
from uuid import uuid1

from graphviz import Digraph

from .styling import CONNECT_STYLE_ATTRIBUTES, ConnectStyle


class Node:
    def __init__(self, id=None) -> None:
        if id is None:
            self.id = str(uuid1())
        else:
            self.id = id

    def _render(self, graph: Digraph):
        pass


class NodeWithName(Node):
    def __init__(self, name: str = "") -> None:
        super().__init__()
        self.name = name

    def _render(self, graph: Digraph):
        graph.node(self.id, label=self.name)


class PolygonNode(NodeWithName):
    def __init__(self, name: str = "") -> None:
        super().__init__(name)

        self.n = Node(f"{self.id}:n")
        self.w = Node(f"{self.id}:w")
        self.s = Node(f"{self.id}:s")
        self.e = Node(f"{self.id}:e")
        self.ne = Node(f"{self.id}:ne")
        self.se = Node(f"{self.id}:se")
        self.sw = Node(f"{self.id}:sw")
        self.nw = Node(f"{self.id}:nw")
        self.c = Node(f"{self.id}:c")


class Diagram(NodeWithName):
    def __init__(self, name="", direction="LR", output_format="pdf"):
        super().__init__(name)
        self.graph = Digraph(name=f"cluster_{self.id}", format=output_format)
        self.graph.attr(
            label=self.name,
            rankdir=direction,
            fontname="Consolas",
            shape="box",
            style="filled, rounded",
            color="lightblue",
        )
        self.nodes = {}

    def connect(self, n1: Node, n2: Node, label="", style=ConnectStyle.STANDARD):
        self.graph.edge(n1.id, n2.id, label=label, **CONNECT_STYLE_ATTRIBUTES[style])

    def connect_multiple(self, node_list: list, style=ConnectStyle.STANDARD):
        n1: Node
        n2: Node
        for nodes in node_list:
            if len(nodes) < 3:
                nodes.append("")
            if len(nodes) < 4:
                nodes.append(ConnectStyle.STANDARD)
            n1, n2, label, style = nodes
            self.connect(n1, n2, label, style=style)

    # Only if it is a subgraph
    def _render(self, _):
        # Render the contents
        for node in self.nodes.values():
            node._render(self.graph)
            if isinstance(node, Diagram):
                self.graph.subgraph(node.graph)

    def render(self, filepath, view=False):
        self._render(None)
        self.graph.render(filepath, view=view)
        os.remove(filepath)

    def __setattr__(self, __name: str, __value) -> None:
        if isinstance(__value, Node):
            self.nodes[__value.id] = __value
        super().__setattr__(__name, __value)
