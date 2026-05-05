# backend/api_server.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import os

from backend.gemini_client    import select_best_bypass_with_llm
from backend.sumo_converter   import export_to_sumo_xml
from backend.osm_fetcher      import fetch_osm_area, OverpassError
from backend.traffic_sim      import simulate_traffic, compare_simulations
from backend.geometry_utils   import find_bypass_candidates

app = FastAPI(title="BDO Optima API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


def _parse_toon(toon: str):
    nodes, edges = [], []
    for line in toon.split("\n"):
        parts = line.strip().split(";")
        if parts[0] == "NODE" and len(parts) >= 4:
            try:
                node = {"id": parts[1],
                        "x": float(parts[2]),
                        "y": float(parts[3])}
                if len(parts) >= 6:
                    try:
                        node["lat"] = float(parts[4])
                        node["lon"] = float(parts[5])
                    except ValueError:
                        pass
                nodes.append(node)
            except ValueError:
                continue
        elif parts[0] == "EDGE" and len(parts) >= 4:
            edges.append({
                "id":       parts[1],
                "from":     parts[2],
                "to":       parts[3],
                "name":     parts[4] if len(parts) >= 5 else "",
                "highway":  parts[5] if len(parts) >= 6 else "",
                "maxspeed": int(parts[6]) if len(parts) >= 7 and parts[6].isdigit() else 40,
                "oneway":   (len(parts) >= 8 and parts[7] == "1"),
            })
    return nodes, edges


def _run_pipeline(raw_toon_data: str, source_label: str,
                  num_trips: int = 300,
                  buildings_local: list = None,
                  buildings_geo: list = None) -> dict:
    """
    Genişletilmiş pipeline:
      1. Önce-simülasyonu (darboğazları bul)
      2. Geometrik aday üretimi (binadan geçmeyen, açısı uygun, vs.)
      3. AI'ya FİLTRELENMİŞ aday listesi — en iyisini seç
      4. Sonra-simülasyonu
      5. Önce/sonra kıyası + SUMO export
    """
    nodes_before, edges_before = _parse_toon(raw_toon_data)
    buildings_local = buildings_local or []
    buildings_geo = buildings_geo or []

    # Adım 1: Önce simülasyonu
    print(f"[SIM] Önce — {num_trips} sürücü...")
    sim_before = simulate_traffic(nodes_before, edges_before,
                                  num_trips=num_trips, seed=42)
    print(f"[SIM] Max yük: {sim_before['max_load']}, "
          f"Ort: {sim_before['avg_load']}, "
          f"Başarısız: {sim_before['failed_trips']}/{num_trips}")

    # Adım 2: Geometrik aday üretimi
    print(f"[GEOM] Bypass adayları üretiliyor "
          f"({len(buildings_local)} bina kontrol ediliyor)...")
    bottleneck_edge_ids = [eid for eid, _ in sim_before["top_bottlenecks"]]
    candidates = find_bypass_candidates(
        nodes_before, edges_before, buildings_local,
        bottleneck_edges=bottleneck_edge_ids,
        max_bypass_length=250.0,
        min_graph_distance=4,
        min_angle_deg=20.0,
        max_candidates=15,
    )
    print(f"[GEOM] {len(candidates)} geçerli aday üretildi")
    if candidates:
        print(f"[GEOM] En iyi 3:")
        for c in candidates[:3]:
            print(f"        {c[0]} ↔ {c[1]} (uzunluk={c[2]}m, skor={c[3]})")

    final_toon_data = raw_toon_data
    ai_bypass_added = False
    sim_after = None
    comparison = None
    chosen_bypass = None

    # Adım 3: AI'a filtreli listeden seç
    if candidates:
        print("[AI] Gemini en iyi adayı seçiyor...")
        try:
            llm_edge = select_best_bypass_with_llm(
                raw_toon_data, sim_before, candidates
            )
        except Exception as e:
            print(f"[AI] Hata: {e}")
            llm_edge = "HATA"

        if llm_edge and llm_edge.startswith("EDGE;"):
            print(f"✅ [AI] Seçim: {llm_edge}")
            parts = llm_edge.split(";")
            if len(parts) >= 4:
                # Bypass'ı tam formatlı ekle
                full_bypass = f"{llm_edge};AI_BYPASS;tertiary;50;0"
                final_toon_data = raw_toon_data.replace(
                    "NETWORK_END", f"{full_bypass}\nNETWORK_END"
                )
                ai_bypass_added = True
                chosen_bypass = {"from": parts[2], "to": parts[3]}

                # Adım 4: Sonra simülasyonu
                nodes_after, edges_after = _parse_toon(final_toon_data)
                print(f"[SIM] Sonra — {num_trips} sürücü...")
                sim_after = simulate_traffic(nodes_after, edges_after,
                                             num_trips=num_trips, seed=42)
                print(f"[SIM] Max yük: {sim_after['max_load']}, "
                      f"Ort: {sim_after['avg_load']}")

                comparison = compare_simulations(sim_before, sim_after)
                imp = comparison["max_load_improvement_pct"]
                if imp > 0:
                    print(f"🎉 [SONUÇ] Max yük %{imp} azaldı!")
                else:
                    print(f"⚠️ [SONUÇ] İyileştirme yok (%{imp})")
        else:
            print("⚠️ [AI] Hata — bypass eklenmedi")
    else:
        print("⚠️ [GEOM] Hiç geçerli aday yok — bypass atlandı")

    # SUMO
    print("[SUMO] XML'ler...")
    sumo_result = export_to_sumo_xml(final_toon_data)

    node_count = sum(1 for ln in final_toon_data.split("\n") if ln.startswith("NODE;"))
    edge_count = sum(1 for ln in final_toon_data.split("\n") if ln.startswith("EDGE;"))

    return {
        "status": "success",
        "source": source_label,
        "data":   final_toon_data,

        # Frontend için bina verisi (Leaflet'te poligon olarak çizilecek)
        "buildings": {
            "geo": buildings_geo,        # [(lat,lon), ...] listesi
            "count": len(buildings_geo),
        },

        # AI seçimi hakkında detay (rapor için)
        "ai_selection": {
            "candidates_count": len(candidates),
            "candidates_top3": [
                {"from": c[0], "to": c[1], "length": c[2], "score": c[3]}
                for c in candidates[:3]
            ] if candidates else [],
            "chosen": chosen_bypass,
        },

        "stats": {
            "nodes": node_count,
            "edges": edge_count,
            "ai_bypass_added": ai_bypass_added,
            "avg_degree": round((2 * edge_count) / node_count, 2) if node_count else 0,
        },

        "traffic": {
            "before": {
                "edge_loads":      sim_before["edge_loads"],
                "max_load":        sim_before["max_load"],
                "avg_load":        sim_before["avg_load"],
                "total_trips":     sim_before["total_trips"],
                "failed_trips":    sim_before["failed_trips"],
                "top_bottlenecks": sim_before["top_bottlenecks"],
            },
            "after": ({
                "edge_loads":      sim_after["edge_loads"],
                "max_load":        sim_after["max_load"],
                "avg_load":        sim_after["avg_load"],
                "total_trips":     sim_after["total_trips"],
                "top_bottlenecks": sim_after["top_bottlenecks"],
            }) if sim_after else None,
            "comparison": comparison,
        },

        "sumo": {
            "nod_xml":         sumo_result["nod_xml"],
            "edg_xml":         sumo_result["edg_xml"],
            "net_xml":         sumo_result["net_xml"],
            "netconvert_path": sumo_result["netconvert_path"],
            "error":           sumo_result["error"],
        },
        "sumo_files_created": sumo_result["nod_xml"] and sumo_result["edg_xml"],
    }


@app.get("/generate")
def generate_network(iterations: int = 3, snapping: float = 5.0, trips: int = 300):
    """L-System sentetik ağ — bina yok."""
    print(f"\n[SİSTEM] L-System → iter={iterations}")

    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    engine_path = os.path.join(project_root, "engine", "engine.exe")

    if not os.path.exists(engine_path):
        raise HTTPException(status_code=500, detail="engine.exe bulunamadı!")

    try:
        result = subprocess.run(
            [engine_path, str(iterations), str(snapping)],
            capture_output=True, text=True, check=True,
        )
        return _run_pipeline(result.stdout, "L-System", trips,
                             buildings_local=[], buildings_geo=[])
    except Exception as e:
        err = str(e)
        if "429" in err:
            return {"status": "error", "message": "Gemini hız sınırı doldu."}
        print(f"❌ {err}")
        raise HTTPException(status_code=500, detail=err)


@app.get("/generate_osm")
def generate_osm_network(
    lat: float = 39.7504, lon: float = 30.4833,
    radius: int = 500, trips: int = 300,
):
    """OSM ağ + binalar."""
    print(f"\n[SİSTEM] OSM → ({lat}, {lon}), r={radius}m")

    if radius > 2000 or radius < 100:
        raise HTTPException(status_code=400, detail="Yarıçap 100-2000m olmalı")

    try:
        # 1+2: Tek HTTP request ile yol + bina + sinyal (paralel sorgu yerine
        # birleşik sorgu — Overpass'a daha az yük, ~%50 hızlı).
        print("[1/5] OSM verisi çekiliyor (yol + bina + sinyal)...")
        osm_data = fetch_osm_area(lat=lat, lon=lon, radius_m=radius)
        raw_toon = osm_data["toon"]
        bldgs = osm_data["buildings"]
        s = osm_data["stats"]
        print(f"[OSM] {s['kept_junctions']} kavşak, {s['edges']} kenar, "
              f"{bldgs['count']} bina, {s['signal_nodes']} sinyal "
              f"({s['fetch_time_seconds']}s)")

        # 3-5: Pipeline (sim + AI + SUMO)
        return _run_pipeline(
            raw_toon, "OSM", trips,
            buildings_local=bldgs["local_polygons"],
            buildings_geo=bldgs["geo_polygons"],
        )

    except OverpassError as e:
        # Kullanıcı dostu — bu mesajı doğrudan frontend gösterecek
        return {"status": "error", "message": str(e)}
    except Exception as e:
        err = str(e)
        if "429" in err:
            return {"status": "error", "message": "Gemini hız sınırı doldu."}
        print(f"❌ {err}")
        raise HTTPException(status_code=500, detail=err)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)