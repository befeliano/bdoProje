#include <iostream>
#include <string>
#include "LSystem.h"
#include "ToonExporter.h"

// argc: terminalden gelen argüman sayısı, argv: argümanların metinleri
int main(int argc, char* argv[]) {
    
    // Varsayılan değerler
    int iterations = 3;
    double snapThreshold = 5.0;

    // Eğer terminalden değer gönderilmişse, onları al
    // Örnek kullanım: engine.exe 4 10.5
    if (argc >= 3) {
        iterations = std::stoi(argv[1]);        // İkinci kelimeyi int'e çevir (İterasyon)
        snapThreshold = std::stod(argv[2]);     // Üçüncü kelimeyi double'a çevir (Snapping)
    }

    // 1. Motoru kur
    LSystem cityGenerator("F");
    
    // Daha karmaşık şehir yapısı için kural
    cityGenerator.addRule('F', "F[+F]F[-F]F");

    // 2. Saf L-Sistemi dizgisini üret (Artık dinamik)
    std::string finalGraphString = cityGenerator.generate(iterations);
    
    // 3. ToonExporter'ı çağır (Artık dinamik Snapping ile)
    std::string toonData = ToonExporter::generateMockToonData(finalGraphString, snapThreshold);
    
    // 4. Saf veriyi Python'un yakalaması için terminale yazdır
    std::cout << toonData;

    return 0;
}