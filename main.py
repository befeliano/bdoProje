import os
import sys
import subprocess

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from backend.toon_parser import ToonParser
from backend.sumo_converter import SumoConverter

def run_bdo_pipeline():
    print("="*50)
    print("🚀 BDO C++ MOTORU VE PYTHON PİPELİNE BAŞLATILIYOR 🚀")
    print("="*50)

    # ---------------------------------------------------------
    # FAZ 1 & 2: C++ Motorunu Çalıştır ve TOON Verisini Yakala
    # ---------------------------------------------------------
    print("\n[FAZ 1] C++ L-Sistemi Motoru (engine.exe) Tetikleniyor...")
    
    # C++ derlenmiş dosyasının yolu (Windows için .exe)
    # Eğer Linux/Mac kullanıyorsan "./engine/engine" yap
    cpp_executable = os.path.join(current_dir, "engine", "engine.exe") 
    
    try:
        # C++ kodunu çalıştır ve terminal çıktısını (TOON verisi) Python'a al
        result = subprocess.run([cpp_executable], capture_output=True, text=True, check=True)
        raw_toon_data = result.stdout
        print("  -> C++ Çıktısı Başarıyla Yakalandı!")
    except FileNotFoundError:
        print(f"[HATA] C++ motoru bulunamadı! Önce CMake ile /engine klasörünü derlediğinden emin ol: {cpp_executable}")
        return
    except subprocess.CalledProcessError as e:
        print(f"[HATA] C++ motoru çöktü: {e}")
        return

    # ---------------------------------------------------------
    # FAZ 3: TOON Parsing ve Doğrulama
    # ---------------------------------------------------------
    print("\n[FAZ 2] Python TOON Ayrıştırıcı (Parser) Devrede...")
    parser = ToonParser()
    parser.parse_string(raw_toon_data)
    print(f"  -> {parser.get_summary()}")

    # ---------------------------------------------------------
    # FAZ 4: SUMO XML Üretimi
    # ---------------------------------------------------------
    print("\n[FAZ 3] SUMO Ağı Derleniyor...")
    sumo_motoru = SumoConverter(parser)
    sumo_motoru.netconvert_path = r"D:\Eclipse\bin\netconvert.exe" 
    sumo_motoru.generate_xml_files()
    sumo_motoru.run_netconvert()

    print("\n" + "="*50)
    print("✅ C++ MOTORU -> PYTHON PARSER -> SUMO AKIŞI TAMAMLANDI!")
    print("="*50)

if __name__ == "__main__":
    run_bdo_pipeline()