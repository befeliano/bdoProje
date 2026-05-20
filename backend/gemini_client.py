import os
import google.generativeai as genai


api_txt_path = os.path.join("..", "API.txt")

if os.path.exists(api_txt_path):
    with open(api_txt_path, "r", encoding="utf-8") as f:
        # Dosya içindeki boşlukları ve satır atlamaları temizleyerek oku
        API_KEY = f.read().strip()
else:
    API_KEY = None
    
if not API_KEY:
    raise RuntimeError(
        "API.txt dosyası bulunamadı veya içi boş!"
    )

genai.configure(api_key=API_KEY)


def select_best_bypass_with_llm(toon_data, sim_result, candidates):
    """
    AI'a açık uçlu soru SORMUYORUZ.
    Önceden filtrelenmiş geçerli adaylar listesinden EN İYİSİNİ seçtiriyoruz.

    Args:
        toon_data: ağ verisi (referans için)
        sim_result: trafik simülasyonu sonucu (darboğaz listesi)
        candidates: [(node_a, node_b, length, score), ...] (geometry_utils'tan)

    Returns:
        "EDGE;LLM_BYPASS_1;Nx;Ny" veya "HATA"
    """
    if not candidates:
        print("[AI] Hiç geçerli aday yok, AI çağrılmıyor")
        return "HATA"

    try:
        model = genai.GenerativeModel('gemini-2.5-flash-lite')

        bottlenecks = sim_result.get("top_bottlenecks", [])
        max_load = sim_result.get("max_load", 0)
        avg_load = sim_result.get("avg_load", 0)

        edge_to_nodes = {}
        for line in toon_data.split("\n"):
            if line.startswith("EDGE;"):
                parts = line.split(";")
                if len(parts) >= 4:
                    edge_to_nodes[parts[1]] = (parts[2], parts[3])

        bottleneck_text = ""
        for edge_id, load in bottlenecks[:5]:
            if edge_id in edge_to_nodes:
                src, dst = edge_to_nodes[edge_id]
                bottleneck_text += f"  - {edge_id} ({src}↔{dst}): {load} araç\n"

        candidate_text = ""
        for i, (a, b, length, score) in enumerate(candidates, 1):
            candidate_text += f"  {i}. {a} ↔ {b}  (uzunluk: {length}m)\n"

        prompt = f"""
Sen bir trafik mühendisisin ve bypass yolu seçimi yapacaksın.

DURUM:
- Maksimum yük: {max_load} araç (darboğaz)
- Ortalama yük: {avg_load} araç

EN SIKIŞIK YOLLAR:
{bottleneck_text}

Önümüzde {len(candidates)} adet GEOMETRİK OLARAK GEÇERLİ aday var.
Bu adaylar zaten şu kriterleri karşılıyor:
✓ Hiçbiri binadan geçmiyor
✓ Hepsi mantıklı uzunlukta (30-250m)
✓ Hepsi açısal olarak uygun (mevcut yollarla en az 20° açı)

ADAYLAR:
{candidate_text}

GÖREVİN: Bu adaylardan EN İYİSİNİ seç. En iyi aday:
- Yukarıdaki darboğazlara EN YAKIN olan
- Mümkünse darboğaz kenarlarının uçlarındaki düğümleri kullanan
- Trafiği en çok dağıtacağına inandığın

ÇIKTI FORMATI: SADECE şu satır, başka hiçbir şey yazma:
EDGE;LLM_BYPASS_1;[secilen_node_a];[secilen_node_b]

Örnek doğru çıktı: EDGE;LLM_BYPASS_1;N12;N47
"""

        response = model.generate_content(prompt)
        yanit = response.text.strip()

        if yanit.startswith("```"):
            lines = [ln for ln in yanit.split("\n")
                     if ln.strip() and not ln.strip().startswith("```")]
            yanit = lines[0] if lines else yanit

        if not yanit.startswith("EDGE;"):
            print(f"[AI] Geçersiz format: {yanit[:80]}")
            best = candidates[0]
            return f"EDGE;LLM_BYPASS_1;{best[0]};{best[1]}"

        parts = yanit.split(";")
        if len(parts) < 4:
            print(f"[AI] Eksik alan: {yanit}")
            best = candidates[0]
            return f"EDGE;LLM_BYPASS_1;{best[0]};{best[1]}"

        chosen_a, chosen_b = parts[2].strip(), parts[3].strip()
        valid_pairs = {frozenset([a, b]) for a, b, _, _ in candidates}

        if frozenset([chosen_a, chosen_b]) not in valid_pairs:
            print(f"[AI] Aday listesinde olmayan seçim: {chosen_a}-{chosen_b}")
            print(f"[AI] Fallback: en yüksek skorlu aday")
            best = candidates[0]
            return f"EDGE;LLM_BYPASS_1;{best[0]};{best[1]}"

        return f"EDGE;LLM_BYPASS_1;{chosen_a};{chosen_b}"

    except Exception as e:
        print(f"[GEMINI HATA] {e}")
        if candidates:
            best = candidates[0]
            print(f"[AI] Fallback: heuristik en iyi aday")
            return f"EDGE;LLM_BYPASS_1;{best[0]};{best[1]}"
        return "HATA"


# Geri uyumluluk
def optimize_network_with_llm(toon_data, sim_result=None):
    print("[AI] UYARI: optimize_network_with_llm doğrudan çağrıldı")
    return "HATA"