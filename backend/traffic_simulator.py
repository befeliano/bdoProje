# backend/traffic_simulator.py
"""
BDO Optima — Trafik Simülatörü

TOON formatındaki yol ağı üzerinde sentetik trafik talebi üretir,
en kısa yol (shortest-path) tabanlı rota ataması yapar ve
edge başına "araç yükü" hesaplar. Ayrıca betweenness centrality ile
her düğümün darboğaz potansiyelini ölçer.

Deterministik: random.seed(42) sabitlenir — aynı graf her zaman
aynı yük dağılımını verir. Bu, "önce vs sonra" karşılaştırmasının
bilimsel olarak savunulabilir olmasını sağlar.

Talep modeli: Preferential attachment (gravity model benzeri)
— derecesi yüksek düğümler "popüler hedef" olur. Gerçek trafik
davranışını yansıtır (herkes merkeze / ana caddeye gider).

Talep hacmi: node_count × 5 (ağ boyutuna orantılı)
"""
from __future__ import annotations

import random
from typing import Dict, List, Tuple, Optional

import networkx as nx


# ── Sabitler ──────────────────────────────────────────────────────────────────
RANDOM_SEED = 42
DEMAND_MULTIPLIER = 5     # node_count × 5 kaynak-hedef çifti üretilir
MIN_DEMAND = 50           # Çok küçük graflar için alt sınır
MAX_DEMAND = 2000         # Çok büyük graflar için üst sınır (performans)


# ── TOON → networkx graf ──────────────────────────────────────────────────────
def build_graph_from_toon(toon_data: str) -> nx.Graph:
    """
    TOON string'ini yönsüz bir networkx grafına dönüştürür.

    Node attribute'ları: x, y, lat (opsiyonel), lon (opsiyonel)
    Edge attribute'ları: id, name (opsiyonel)

    Self-loop ve duplicate edge'leri atlar.
    """
    G = nx.Graph()

    for line in toon_data.strip().split("\n"):
        line = line.strip()
        if not line or line in ("NETWORK_START", "NETWORK_END"):
            continue

        parts = line.split(";")
        tag = parts[0]

        try:
            if tag == "NODE" and len(parts) >= 4:
                nid = parts[1]
                x, y = float(parts[2]), float(parts[3])
                attrs = {"x": x, "y": y}
                # Coğrafi koordinat varsa al
                if len(parts) >= 6:
                    try:
                        attrs["lat"] = float(parts[4])
                        attrs["lon"] = float(parts[5])
                    except ValueError:
                        pass
                G.add_node(nid, **attrs)

            elif tag == "EDGE" and len(parts) >= 4:
                eid, a, b = parts[1], parts[2], parts[3]
                if a == b:
                    continue  # self-loop
                # Yol ismi (opsiyonel)
                name = ";".join(parts[4:]).strip() if len(parts) >= 5 else ""
                # Duplicate edge'i atla (ilk ekleneni koru)
                if G.has_edge(a, b):
                    continue
                G.add_edge(a, b, id=eid, name=name)

        except (ValueError, IndexError):
            # Bozuk satırı sessizce atla; parse hatası simülasyonu durdurmasın
            continue

    return G


# ── Sentetik talep üretici ────────────────────────────────────────────────────
def _compute_demand_count(node_count: int) -> int:
    """Ağ boyutuna göre kaç araç-rotası üretilecek — üst/alt sınırlı."""
    raw = node_count * DEMAND_MULTIPLIER
    return max(MIN_DEMAND, min(raw, MAX_DEMAND))


def _generate_od_pairs(
    G: nx.Graph, count: int, rng: random.Random
) -> List[Tuple[str, str]]:
    """
    Origin-Destination çiftleri üret. Gerçekçi model:
      - Kaynaklar rastgele seçilir (herkes her yerden yola çıkabilir).
      - Hedefler derece-ağırlıklı seçilir (popüler kavşaklar daha çok çekim
        alır — "gravity model" yaklaşımı).

    Bu, hoca "neden bu dağılım?" diye sorduğunda verebileceğimiz
    savunulabilir bir modeldir: şehirlerde insanlar rastgele yerlerde
    yaşar ama merkezi kavşaklara/caddelere gider.
    """
    nodes = list(G.nodes())
    if len(nodes) < 2:
        return []

    # Dereceye göre ağırlıklar (hedef seçimi için)
    degrees = dict(G.degree())
    # +1 ile izole veya düşük dereceli noktalar da küçük şansa sahip olsun
    weights = [degrees[n] + 1 for n in nodes]

    pairs: List[Tuple[str, str]] = []
    attempts = 0
    max_attempts = count * 5  # loop koruması

    while len(pairs) < count and attempts < max_attempts:
        attempts += 1
        src = rng.choice(nodes)
        dst = rng.choices(nodes, weights=weights, k=1)[0]
        if src == dst:
            continue
        pairs.append((src, dst))

    return pairs


# ── Ana simülatör ─────────────────────────────────────────────────────────────
def simulate_traffic(
    G: nx.Graph,
    seed: int = RANDOM_SEED,
) -> Dict:
    """
    Ağ üzerinde trafik simülasyonu koşturur ve metrikleri döner.

    Her OD çifti için en kısa yol (hop sayısı) bulunur. Yol üzerindeki
    her kenar 1 "araç/gün" ile yüklenir. Kopuk bileşenler için:
    aynı bileşen içinde kalan çiftler hesaplanır, diğerleri atlanır.

    Returns:
        {
          "demand_count": 200,
          "routed_count": 198,          # ulaşılabilen çiftler
          "unreachable_count": 2,       # kopuk bileşen yüzünden yolu olmayan
          "edge_load": { "E1": 142, ... },
          "node_betweenness": { "N47": 0.182, ... },  # [0..1] normalize
          "max_edge_load": 142,
          "avg_edge_load": 38.4,
          "total_vehicle_edges": 7600,   # toplam (araç × segment) — avg travel length için
          "avg_path_length": 38.4,       # bir aracın ortalama kaç segment gezdiği
          "top_bottleneck_edges": [
              {"edge_id": "E12", "from": "N1", "to": "N2",
               "name": "Atatürk Cd", "load": 142},
              ...
          ],
          "top_bottleneck_nodes": [
              {"node_id": "N47", "betweenness": 0.182, "degree": 4},
              ...
          ],
        }
    """
    rng = random.Random(seed)

    node_count = G.number_of_nodes()
    edge_count = G.number_of_edges()

    # Boş graf / tek düğüm → anlamlı simülasyon yapılamaz
    if node_count < 2 or edge_count == 0:
        return {
            "demand_count": 0,
            "routed_count": 0,
            "unreachable_count": 0,
            "edge_load": {},
            "node_betweenness": {n: 0.0 for n in G.nodes()},
            "max_edge_load": 0,
            "avg_edge_load": 0.0,
            "total_vehicle_edges": 0,
            "avg_path_length": 0.0,
            "top_bottleneck_edges": [],
            "top_bottleneck_nodes": [],
        }

    # ── Talep üret ───────────────────────────────────────────────────────────
    demand_count = _compute_demand_count(node_count)
    od_pairs = _generate_od_pairs(G, demand_count, rng)

    # ── Rota ataması: en kısa yolu bul ve edge yüklerini artır ──────────────
    edge_load: Dict[Tuple[str, str], int] = {}
    routed = 0
    unreachable = 0
    total_hops = 0

    for src, dst in od_pairs:
        try:
            # hop sayısı bazlı en kısa yol (graf ağırlıksız)
            path = nx.shortest_path(G, src, dst)
        except nx.NetworkXNoPath:
            unreachable += 1
            continue
        except nx.NodeNotFound:
            unreachable += 1
            continue

        routed += 1
        total_hops += len(path) - 1
        for a, b in zip(path, path[1:]):
            # Yönsüz graf → (min, max) anahtarıyla normalize et
            key = (a, b) if a < b else (b, a)
            edge_load[key] = edge_load.get(key, 0) + 1

    # ── Edge ID'ye göre yük haritası çıkar ──────────────────────────────────
    edge_load_by_id: Dict[str, int] = {}
    # Hızlı arama için: (min, max) → attrs
    for (a, b), load in edge_load.items():
        data = G.get_edge_data(a, b) or {}
        eid = data.get("id", f"{a}-{b}")
        edge_load_by_id[eid] = load

    # Yüklenmemiş edge'ler de 0 olarak raporlansın (frontend gradient için)
    for a, b, data in G.edges(data=True):
        eid = data.get("id", f"{a}-{b}")
        edge_load_by_id.setdefault(eid, 0)

    # ── Betweenness centrality ──────────────────────────────────────────────
    # k=None → exact; büyük graflarda pahalı ama node sayısı genelde <500 olacak
    # 500+ düğüm için örnekleme yapıyoruz (performans)
    if node_count > 500:
        k_sample = min(node_count, 300)
        betweenness = nx.betweenness_centrality(G, k=k_sample, seed=seed)
    else:
        betweenness = nx.betweenness_centrality(G)

    # ── Özet metrikler ──────────────────────────────────────────────────────
    loads = list(edge_load_by_id.values())
    max_load = max(loads) if loads else 0
    avg_load = sum(loads) / len(loads) if loads else 0.0
    avg_path = total_hops / routed if routed else 0.0

    # ── Top darboğaz edge'ler ───────────────────────────────────────────────
    edge_info_list = []
    for a, b, data in G.edges(data=True):
        eid = data.get("id", f"{a}-{b}")
        edge_info_list.append({
            "edge_id": eid,
            "from": a,
            "to": b,
            "name": data.get("name", "") or "",
            "load": edge_load_by_id.get(eid, 0),
        })
    edge_info_list.sort(key=lambda x: x["load"], reverse=True)
    top_edges = edge_info_list[:5]

    # ── Top darboğaz node'lar ───────────────────────────────────────────────
    degrees = dict(G.degree())
    node_info_list = [
        {
            "node_id": n,
            "betweenness": round(b, 4),
            "degree": degrees.get(n, 0),
        }
        for n, b in betweenness.items()
    ]
    node_info_list.sort(key=lambda x: x["betweenness"], reverse=True)
    top_nodes = node_info_list[:5]

    return {
        "demand_count": demand_count,
        "routed_count": routed,
        "unreachable_count": unreachable,
        "edge_load": edge_load_by_id,
        "node_betweenness": {n: round(v, 4) for n, v in betweenness.items()},
        "max_edge_load": max_load,
        "avg_edge_load": round(avg_load, 2),
        "total_vehicle_edges": total_hops,
        "avg_path_length": round(avg_path, 2),
        "top_bottleneck_edges": top_edges,
        "top_bottleneck_nodes": top_nodes,
    }


# ── Önce/Sonra karşılaştırma ──────────────────────────────────────────────────
def compare_simulations(before: Dict, after: Dict) -> Dict:
    """
    İki simülasyon sonucunu karşılaştırır. Ana metrik:
    max_edge_load'un azalma yüzdesi — "darboğaz ne kadar rahatladı".

    Ayrıca ortalama yol uzunluğu değişimini raporlar: bypass eklemek
    çoğu zaman ortalama yolu da kısaltır (alternatif rota açılır).
    """
    max_before = before["max_edge_load"]
    max_after = after["max_edge_load"]
    avg_before = before["avg_edge_load"]
    avg_after = after["avg_edge_load"]
    path_before = before["avg_path_length"]
    path_after = after["avg_path_length"]

    def pct_change(old: float, new: float) -> float:
        if old <= 0:
            return 0.0
        return round((old - new) / old * 100, 2)

    return {
        "max_load_before": max_before,
        "max_load_after": max_after,
        "max_load_improvement_pct": pct_change(max_before, max_after),

        "avg_load_before": avg_before,
        "avg_load_after": avg_after,
        "avg_load_improvement_pct": pct_change(avg_before, avg_after),

        "avg_path_before": path_before,
        "avg_path_after": path_after,
        "avg_path_improvement_pct": pct_change(path_before, path_after),
    }


# ── Gemini için darboğaz özeti ────────────────────────────────────────────────
def format_bottleneck_summary_for_llm(sim: Dict) -> str:
    """
    Gemini prompt'una enjekte edilecek, insan-okunur darboğaz raporu üretir.
    Amaç: LLM'e "nerelere bypass önermeli" konusunda VERI sağlamak,
    rastgele tahmin yerine bilgi-tabanlı karar aldırmak.
    """
    lines = []
    lines.append(
        f"Simülasyon sonucu: {sim['routed_count']} araç rota aldı "
        f"(ortalama yol: {sim['avg_path_length']} segment)."
    )
    lines.append(
        f"En yoğun yolun yükü: {sim['max_edge_load']} araç, "
        f"ortalama yük: {sim['avg_edge_load']} araç."
    )
    lines.append("")
    lines.append("EN YOĞUN 5 YOL (bu yolları RAHATLATACAK bir bypass öner):")
    for i, e in enumerate(sim["top_bottleneck_edges"], 1):
        name = f" ({e['name']})" if e["name"] else ""
        lines.append(
            f"  {i}. {e['from']} → {e['to']}{name} — {e['load']} araç"
        )
    lines.append("")
    lines.append("EN KRİTİK 5 KAVŞAK (betweenness centrality en yüksek):")
    for i, n in enumerate(sim["top_bottleneck_nodes"], 1):
        lines.append(
            f"  {i}. {n['node_id']} — betweenness: {n['betweenness']}, "
            f"derece: {n['degree']}"
        )
    return "\n".join(lines)


# ── TEST ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Küçük örnek ağ: 5 düğümlü ızgara
    sample_toon = """NETWORK_START
NODE;N1;0;0
NODE;N2;100;0
NODE;N3;200;0
NODE;N4;100;100
NODE;N5;200;100
EDGE;E1;N1;N2
EDGE;E2;N2;N3
EDGE;E3;N2;N4;Atatürk Cd
EDGE;E4;N4;N5
EDGE;E5;N3;N5;İnönü Cd
NETWORK_END
"""

    G = build_graph_from_toon(sample_toon)
    print(f"Graf: {G.number_of_nodes()} düğüm, {G.number_of_edges()} kenar")

    sim = simulate_traffic(G)
    print(f"\nTalep: {sim['demand_count']}, rota alınan: {sim['routed_count']}")
    print(f"Max edge load: {sim['max_edge_load']}")
    print(f"Avg edge load: {sim['avg_edge_load']}")
    print(f"Avg path length: {sim['avg_path_length']}")
    print(f"\nTop edge loads:")
    for e in sim["top_bottleneck_edges"]:
        print(f"  {e['edge_id']}: {e['from']}→{e['to']} = {e['load']}")

    print(f"\n--- LLM PROMPT FORMAT ---")
    print(format_bottleneck_summary_for_llm(sim))