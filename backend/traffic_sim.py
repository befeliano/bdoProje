# backend/traffic_sim.py
"""
Trafik simülatörü — YÖNLÜ graf + zaman tabanlı en kısa yol.

İki yenilik:
  1. Tek yönlü sokakları doğru modelle (oneway=1 → sadece a→b kenar)
  2. Dijkstra ağırlığı = mesafe / hız_limiti (yani SÜRE),
     eski sürümde sadece mesafeydi → otoban ile yan sokak aynı görünüyordu

Eski TOON formatıyla geri uyumlu (oneway/maxspeed yoksa varsayılan kullanılır).
"""
import random
import math
import heapq
from collections import defaultdict


def _build_graph(nodes, edges):
    """
    Yönlü komşuluk listesi kurar.

    edge dict yapısı:
        {"id": ..., "from": ..., "to": ...,
         "oneway": bool (varsayılan False),
         "maxspeed": int km/h (varsayılan 40)}

    Returns:
        adj: {node_id: [(neighbor_id, travel_time, edge_id), ...]}
        edge_meta: {edge_id: {"from", "to", "length", "maxspeed", "oneway"}}
    """
    node_pos = {n["id"]: (n["x"], n["y"]) for n in nodes}
    adj = defaultdict(list)
    edge_meta = {}

    for e in edges:
        a, b = e["from"], e["to"]
        if a not in node_pos or b not in node_pos:
            continue
        ax, ay = node_pos[a]
        bx, by = node_pos[b]
        length = math.hypot(bx - ax, by - ay)  # metre cinsinden
        if length < 1e-6:
            continue

        maxspeed = e.get("maxspeed", 40)        # km/h
        oneway = e.get("oneway", False)

        # Süre = mesafe / hız (m / (km/h * 1000/3600)) → saniye
        speed_ms = maxspeed * 1000.0 / 3600.0   # m/s
        travel_time = length / speed_ms          # saniye

        adj[a].append((b, travel_time, e["id"]))
        if not oneway:
            adj[b].append((a, travel_time, e["id"]))   # ters yön de aç

        edge_meta[e["id"]] = {
            "from": a, "to": b,
            "length": length,
            "maxspeed": maxspeed,
            "oneway": oneway,
            "travel_time": travel_time,
        }

    return adj, edge_meta


def _dijkstra(adj, source):
    """Kaynaktan tüm düğümlere en kısa SÜRE."""
    dist = {source: 0}
    prev_edge = {source: None}
    heap = [(0, source)]

    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, math.inf):
            continue
        for v, w, eid in adj[u]:
            nd = d + w
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                prev_edge[v] = (u, eid)
                heapq.heappush(heap, (nd, v))
    return dist, prev_edge


def _reconstruct_edges(prev_edge, target):
    path = []
    cur = target
    while prev_edge.get(cur) is not None:
        parent, eid = prev_edge[cur]
        path.append(eid)
        cur = parent
    return path


def simulate_traffic(nodes, edges, num_trips=300, seed=42):
    """
    Ana simülasyon — yönlü graf, zaman tabanlı.
    """
    rng = random.Random(seed)
    adj, edge_meta = _build_graph(nodes, edges)

    if not edge_meta:
        return _empty_result(seed)

    # Zayıf-bağlı bileşenleri görmek için tüm düğüm id'lerini topla
    all_node_ids = set(adj.keys())
    # Hedef olabilecek düğümler de adj'de olmasa olur; node listesinden alalım
    for n in nodes:
        all_node_ids.add(n["id"])
    node_ids = list(all_node_ids)

    if len(node_ids) < 2:
        return _empty_result(seed)

    edge_loads = defaultdict(int)
    successful = 0
    failed = 0
    origin_cache = {}

    for _ in range(num_trips):
        origin = rng.choice(node_ids)
        dest = rng.choice(node_ids)
        if origin == dest:
            continue

        if origin not in origin_cache:
            origin_cache[origin] = _dijkstra(adj, origin)
        dist, prev_edge = origin_cache[origin]

        if dest not in dist:
            failed += 1   # yönlü grafta destinasyona ulaşılamayabilir
            continue

        for eid in _reconstruct_edges(prev_edge, dest):
            edge_loads[eid] += 1
        successful += 1

    loads_list = list(edge_loads.values())
    max_load = max(loads_list) if loads_list else 0
    avg_load = (sum(loads_list) / len(loads_list)) if loads_list else 0
    top = sorted(edge_loads.items(), key=lambda kv: -kv[1])[:5]

    return {
        "edge_loads":      dict(edge_loads),
        "max_load":        max_load,
        "avg_load":        round(avg_load, 2),
        "total_trips":     successful,
        "failed_trips":    failed,
        "top_bottlenecks": top,
        "seed":            seed,
    }


def _empty_result(seed):
    return {
        "edge_loads": {}, "max_load": 0, "avg_load": 0,
        "total_trips": 0, "failed_trips": 0,
        "top_bottlenecks": [], "seed": seed,
    }


def compare_simulations(before, after):
    max_b, max_a = before["max_load"], after["max_load"]
    avg_b, avg_a = before["avg_load"], after["avg_load"]

    def pct_change(a, b):
        if a == 0:
            return 0.0
        return round((b - a) / a * 100, 1)

    return {
        "max_load_before":          max_b,
        "max_load_after":           max_a,
        "max_load_improvement_pct": -pct_change(max_b, max_a),
        "avg_load_before":          avg_b,
        "avg_load_after":           avg_a,
        "avg_load_improvement_pct": -pct_change(avg_b, avg_a),
        "bottlenecks_before":       before["top_bottlenecks"],
        "bottlenecks_after":        after["top_bottlenecks"],
    }


if __name__ == "__main__":
    # Test: 3 düğüm, biri tek yönlü
    test_nodes = [
        {"id": "A", "x": 0,   "y": 0},
        {"id": "B", "x": 100, "y": 0},
        {"id": "C", "x": 0,   "y": 100},
    ]
    test_edges = [
        {"id": "E1", "from": "A", "to": "B", "maxspeed": 50, "oneway": False},
        {"id": "E2", "from": "B", "to": "C", "maxspeed": 30, "oneway": True},
        {"id": "E3", "from": "A", "to": "C", "maxspeed": 30, "oneway": False},
    ]
    r = simulate_traffic(test_nodes, test_edges, num_trips=200)
    print("Edge yükleri:", r["edge_loads"])
    print("Max yük:", r["max_load"])
    print("Failed (ulaşılamaz OD):", r["failed_trips"])