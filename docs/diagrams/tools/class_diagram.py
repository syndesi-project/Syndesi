from uuid import uuid1

from graphviz import Digraph


class Node:
    def __init__(self) -> None:
        self.id = str(uuid1())

    def _render(self, graph: Digraph):
        pass


class NodeWithName(Node):
    def __init__(self, name: str = "") -> None:
        super().__init__()
        self.name = name

    def _render(self, graph: Digraph):
        graph.node(self.id, label=self.name)


class Method(NodeWithName):
    def __init__(self, name):
        super().__init__(name)


class User(NodeWithName):
    def __init__(self, name: str = "User") -> None:
        super().__init__(name)


class Class(NodeWithName):
    def __init__(self, name):
        super().__init__(name)
        self.methods = []
        self._port_count = 1

    def _add_method(self, method_obj):
        self.methods.append(method_obj)

    def _next_port(self):
        port = f"m{self._port_count}"
        self._port_count += 1
        return port

    def to(self, other_class, label=""):
        self.graph._add_edge(self.id, other_class.id, label)

    def __setattr__(self, __name: str, __value) -> None:
        super().__setattr__(__name, __value)

    def _render(self, graph: Digraph):
        rows = "".join(
            f'<TR><TD PORT="{method.port}">{method.name}</TD></TR>'
            for method in self.methods
        )
        label = f"""<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0">
            <TR><TD BGCOLOR="lightblue"><B>{self.name}</B></TD></TR>
            {rows}
        </TABLE>>"""
        graph.node(self.id, label=label)


class Diagram:
    def __init__(self, name="ClassDiagram", direction="LR", output_format="pdf"):
        self.name = name
        self.graph = Digraph(name=name, format=output_format)
        self.graph.attr(rankdir=direction, fontname="Consolas")
        self.graph.attr("node", shape="plaintext", fontname="Consolas")
        self.nodes = {}

    def _add_class(self, class_obj):
        self.nodes[class_obj.id] = class_obj

    def connect(self, n1: Node, n2: Node, label=""):
        self.graph.edge(n1.id, n2.id, label=label)

    def connect_multiple(self, node_list: list):
        n1: Node
        n2: Node
        for n1, n2 in node_list:
            self.connect(n1, n2)

    def render(self, filename="diagram", view=True):
        for node in self.nodes.values():
            node._render(self.graph)
        self.graph.render(filename, view=view)

    def __setattr__(self, __name: str, __value) -> None:
        if isinstance(__value, Node):
            self.nodes[__value.id] = __value
        super().__setattr__(__name, __value)
