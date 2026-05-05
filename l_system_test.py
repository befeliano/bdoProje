import math
import matplotlib.pyplot as plt

class LSystemEngine:
    def __init__(self, axiom, rules):
        self.axiom = axiom
        self.rules = rules

    def generate_string(self, iterations):
        current = self.axiom
        for _ in range(iterations):
            next_str = "".join([self.rules.get(c, c) for c in current])
            current = next_str
        return current

class ToonConverterPro:
    def __init__(self, distance=20.0, angle=90.0, snap_threshold=5.0):
        self.distance = distance
        self.angle = angle
        self.snap_threshold = snap_threshold
        self.nodes = {} # id: (x, y)
        self.edges = [] # list of dicts

    def _get_closest_node(self, x, y):
        """Snapping: Yakındaki düğümü bulur, yoksa None döner."""
        for node_id, (nx, ny) in self.nodes.items():
            if math.hypot(x - nx, y - ny) < self.snap_threshold:
                return node_id
        return None

    def process_string(self, l_string):
        self.nodes = {"N1": (0.0, 0.0)}
        self.edges = []
        stack = []
        curr_x, curr_y, curr_angle = 0.0, 0.0, 0.0
        curr_node_id = "N1"
        node_count = 1

        for char in l_string:
            if char == 'F':
                rad = math.radians(curr_angle)
                new_x = round(curr_x + self.distance * math.cos(rad), 2)
                new_y = round(curr_y + self.distance * math.sin(rad), 2)

                # Snapping kontrolü
                target_node = self._get_closest_node(new_x, new_y)
                
                if target_node is None:
                    node_count += 1
                    target_node = f"N{node_count}"
                    self.nodes[target_node] = (new_x, new_y)
                
                # Kendine bağlanmıyorsa kenar ekle
                if curr_node_id != target_node:
                    edge_id = f"E{len(self.edges) + 1}"
                    self.edges.append({"id": edge_id, "from": curr_node_id, "to": target_node})
                
                curr_x, curr_y, curr_node_id = self.nodes[target_node][0], self.nodes[target_node][1], target_node

            elif char == '+': curr_angle += self.angle
            elif char == '-': curr_angle -= self.angle
            elif char == '[': stack.append((curr_x, curr_y, curr_angle, curr_node_id))
            elif char == ']': 
                curr_x, curr_y, curr_angle, curr_node_id = stack.pop()