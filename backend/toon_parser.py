class ToonParser:
    def __init__(self):
        self.nodes = {}  # {'N1': {'x': 0.0, 'y': 0.0}}
        self.edges = []  # [{'id': 'E1', 'from': 'N1', 'to': 'N2'}]

    def parse_string(self, toon_data: str):
        """
        TOON formatındaki metni okur ve Python verilerine dönüştürür.
        """
        print("[PARSER] TOON verisi ayrıştırılıyor...")
        self.nodes.clear()
        self.edges.clear()

        lines = toon_data.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line or line in ["NETWORK_START", "NETWORK_END"]:
                continue

            parts = line.split(';')
            token_type = parts[0]

            try:
                if token_type == "NODE":
                    node_id = parts[1]
                    x, y = float(parts[2]), float(parts[3])
                    self.nodes[node_id] = {'x': x, 'y': y}

                elif token_type == "EDGE":
                    edge_id = parts[1]
                    from_node = parts[2]
                    to_node = parts[3]
                    self.edges.append({'id': edge_id, 'from': from_node, 'to': to_node})

                else:
                    print(f"[UYARI] Bilinmeyen token: {token_type}")

            # DÜZELTME: `except IndexError or ValueError:` Python'da çalışmaz,
            # çünkü `IndexError or ValueError` ifadesi her zaman `IndexError`'a
            # eşittir ve ValueError'lar sessizce yukarı fırlardı. Tuple doğru syntax.
            except (IndexError, ValueError) as e:
                print(f"[HATA] Satır ayrıştırılamadı ({type(e).__name__}): {line}")

    def get_summary(self):
        """Ağ hakkında kısa bir özet döndürür."""
        return f"Toplam Düğüm: {len(self.nodes)}, Toplam Yol: {len(self.edges)}"

    def generate_llm_prompt(self):
        """
        Gemini API'ye gönderilecek olan sıkıştırılmış metni hazırlar.
        """
        prompt = (
            "Aşağıdaki TOON formatındaki şehir trafik ağını incele. "
            "Trafik darboğazlarını çözmek için uygun düğümler arasına 1 adet "
            "'bypass' (kestirme) yol ekle ve sadece yeni eklediğin yolu "
            "'EDGE;...' formatında döndür.\n\n"
        )

        prompt += "Mevcut Ağ:\nNETWORK_START\n"
        for node_id, coords in self.nodes.items():
            prompt += f"NODE;{node_id};{coords['x']};{coords['y']}\n"
        for edge in self.edges:
            prompt += f"EDGE;{edge['id']};{edge['from']};{edge['to']}\n"
        prompt += "NETWORK_END"

        return prompt


# --- TEST KISMI ---
if __name__ == "__main__":
    cpp_output = """
    NETWORK_START
    NODE;N1;0.0;0.0
    NODE;N2;100.0;0.0
    NODE;N3;100.0;50.0
    EDGE;E1;N1;N2
    EDGE;E2;N2;N3
    NETWORK_END
    """

    parser = ToonParser()
    parser.parse_string(cpp_output)

    print("\n[BİLGİ] Ayrıştırma Başarılı!")
    print(parser.get_summary())

    print("\n--- GEMINI API İÇİN HAZIRLANAN PROMPT ---")
    print(parser.generate_llm_prompt())