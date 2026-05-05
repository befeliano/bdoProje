# backend/sumo_converter.py
import xml.etree.ElementTree as ET
from xml.dom import minidom
import os
import subprocess
import shutil

# ── Yardımcı: güzel XML formatı ──────────────────────────────────────────────
def _indent(elem):
    rough = ET.tostring(elem, 'utf-8')
    return minidom.parseString(rough).toprettyxml(indent="  ")


# ── netconvert binary'sini bul ────────────────────────────────────────────────
def _find_netconvert():
    """
    Sistemde netconvert'i arar. Sırasıyla kontrol eder:
      1. PATH'te var mı? (shutil.which — hem Windows hem Linux/Mac)
      2. Windows'ta tipik SUMO kurulum yerleri
      3. Linux'ta tipik kurulum yerleri
    Bulamazsa None döner — fonksiyon sessizce devam eder.
    """
    # PATH'te var mı?
    found = shutil.which("netconvert")
    if found:
        return found

    # Windows tipik kurulum yerleri
    win_paths = [
        r"C:\Program Files (x86)\Eclipse\Sumo\bin\netconvert.exe",
        r"C:\Program Files\Eclipse\Sumo\bin\netconvert.exe",
        r"C:\sumo\bin\netconvert.exe",
    ]
    for p in win_paths:
        if os.path.isfile(p):
            return p

    # Linux / Mac tipik kurulum yerleri
    unix_paths = [
        "/usr/bin/netconvert",
        "/usr/local/bin/netconvert",
        "/opt/sumo/bin/netconvert",
    ]
    for p in unix_paths:
        if os.path.isfile(p):
            return p

    return None


# ── Ana fonksiyon ─────────────────────────────────────────────────────────────
def export_to_sumo_xml(toon_data: str, output_folder: str = "sumo_files") -> dict:
    """
    TOON verisini önce .nod.xml ve .edg.xml'e yazar,
    ardından netconvert ile .net.xml üretmeyi dener.

    Döndürdüğü dict:
        {
            "nod_xml":  True,          # .nod.xml yazıldı mı
            "edg_xml":  True,          # .edg.xml yazıldı mı
            "net_xml":  True/False,    # .net.xml üretildi mi
            "netconvert_path": "...",  # kullanılan binary yolu (yoksa None)
            "error":    None / "..."   # netconvert hata mesajı
        }
    """
    os.makedirs(output_folder, exist_ok=True)

    result = {
        "nod_xml": False,
        "edg_xml": False,
        "net_xml": False,
        "netconvert_path": None,
        "error": None,
    }

    # ── 1. TOON → node / edge listesi ────────────────────────────────────────
    nodes, edges = [], []

    for line in toon_data.strip().split('\n'):
        parts = line.strip().split(';')
        if len(parts) < 2:
            continue
        if parts[0] == 'NODE' and len(parts) >= 4:
            nodes.append({'id': parts[1], 'x': parts[2], 'y': parts[3]})
        elif parts[0] == 'EDGE' and len(parts) >= 4:
            edges.append({'id': parts[1], 'from': parts[2], 'to': parts[3]})

    # ── 2. .nod.xml ──────────────────────────────────────────────────────────
    nod_path = os.path.join(output_folder, "network.nod.xml")
    nodes_root = ET.Element('nodes')
    for n in nodes:
        ET.SubElement(nodes_root, 'node',
                      id=n['id'], x=n['x'], y=n['y'], type="priority")
    with open(nod_path, "w", encoding="utf-8") as f:
        f.write(_indent(nodes_root))
    result["nod_xml"] = True
    print(f"[SUMO] .nod.xml yazıldı → {nod_path} ({len(nodes)} düğüm)")

    # ── 3. .edg.xml ──────────────────────────────────────────────────────────
    edg_path = os.path.join(output_folder, "network.edg.xml")
    edges_root = ET.Element('edges')
    for e in edges:
        ET.SubElement(edges_root, 'edge',
                      id=e['id'],
                      **{'from': e['from'], 'to': e['to'],
                         'numLanes': "2", 'speed': "13.89"})
    with open(edg_path, "w", encoding="utf-8") as f:
        f.write(_indent(edges_root))
    result["edg_xml"] = True
    print(f"[SUMO] .edg.xml yazıldı → {edg_path} ({len(edges)} kenar)")

    # ── 4. netconvert ile .net.xml üret ──────────────────────────────────────
    net_path = os.path.join(output_folder, "network.net.xml")
    netconvert = _find_netconvert()

    if not netconvert:
        print("[SUMO] ⚠️  netconvert bulunamadı — .net.xml atlandı.")
        print("[SUMO]    SUMO PATH'te değilse: https://sumo.dlr.de/docs/Installing")
        result["error"] = "netconvert bulunamadı"
        return result

    result["netconvert_path"] = netconvert
    print(f"[SUMO] netconvert bulundu → {netconvert}")
    print("[SUMO] .net.xml üretiliyor...")

    cmd = [
        netconvert,
        "--node-files", nod_path,
        "--edge-files", edg_path,
        "--output-file", net_path,
        "--no-warnings",          # terminali temiz tut
        "--no-turnarounds",       # U-dönüşü ekleme (daha temiz ağ)
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,           # 30 sn içinde bitmezse zaten büyük bir sorun var
        )

        if proc.returncode == 0:
            net_size_kb = os.path.getsize(net_path) // 1024
            print(f"[SUMO] ✅ .net.xml oluşturuldu → {net_path} ({net_size_kb} KB)")
            result["net_xml"] = True
        else:
            # netconvert bulundu ama hata verdi — stderr'i raporla
            err = proc.stderr.strip() or proc.stdout.strip()
            print(f"[SUMO] ❌ netconvert hata verdi:\n{err}")
            result["error"] = err[:300]  # çok uzun olmasın

    except subprocess.TimeoutExpired:
        print("[SUMO] ❌ netconvert 30 saniyede tamamlanamadı.")
        result["error"] = "timeout"
    except Exception as e:
        print(f"[SUMO] ❌ netconvert çalıştırılamadı: {e}")
        result["error"] = str(e)

    return result