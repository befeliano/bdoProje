#ifndef TOONEXPORTER_H
#define TOONEXPORTER_H

#include <string>

class ToonExporter {
public:
    // SÖZLEŞMEYİ GÜNCELLEDİK: Artık double snapThreshold parametresi de alıyor
    static std::string generateMockToonData(const std::string& lSystemString, double snapThreshold);
};

#endif