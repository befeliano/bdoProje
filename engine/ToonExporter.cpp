#include "ToonExporter.h"
#include <sstream>
#include <stack>
#include <cmath>
#include <vector>
#include <iostream>

struct TurtleState { double x, y, angle; std::string nodeId; };
struct NodeData { std::string id; double x, y; };

// Fonksiyona dışarıdan snapThreshold değerini alacak bir parametre ekledik
std::string ToonExporter::generateMockToonData(const std::string& lSystemString, double snapThreshold) {
    std::stringstream toon;
    std::stack<TurtleState> stateStack;
    std::vector<NodeData> nodes;
    std::vector<std::string> edges;

    double currentX = 0.0, currentY = 0.0, currentAngle = 0.0;
    int nodeCounter = 1, edgeCounter = 1;
    
    std::string currentNode = "N" + std::to_string(nodeCounter++);
    nodes.push_back({currentNode, currentX, currentY});

    double distance = 30.0;  
    double angleStep = 90.0; 
    // const double snapThreshold = 5.0; -> BUNU SİLDİK, artık parametre olarak geliyor.
    const double PI = 3.141592653589793;

    for (char c : lSystemString) {
        if (c == 'F') {
            double rad = currentAngle * PI / 180.0;
            double newX = currentX + distance * cos(rad);
            double newY = currentY + distance * sin(rad);

            newX = std::round(newX * 100.0) / 100.0;
            newY = std::round(newY * 100.0) / 100.0;

            std::string targetNode = "";
            
            for (const auto& n : nodes) {
                double dist = std::hypot(newX - n.x, newY - n.y);
                if (dist < snapThreshold) {
                    targetNode = n.id; 
                    break;
                }
            }

            if (targetNode == "") {
                targetNode = "N" + std::to_string(nodeCounter++);
                nodes.push_back({targetNode, newX, newY});
            }

            if (currentNode != targetNode) {
                edges.push_back("EDGE;E" + std::to_string(edgeCounter++) + ";" + currentNode + ";" + targetNode);
            }

            currentX = newX;
            currentY = newY;
            currentNode = targetNode;
        } 
        else if (c == '+') currentAngle -= angleStep;
        else if (c == '-') currentAngle += angleStep;
        else if (c == '[') stateStack.push({currentX, currentY, currentAngle, currentNode});
        else if (c == ']') {
            TurtleState prevState = stateStack.top();
            stateStack.pop();
            currentX = prevState.x;
            currentY = prevState.y;
            currentAngle = prevState.angle;
            currentNode = prevState.nodeId;
        }
    }

    toon << "NETWORK_START\n";
    for (const auto& n : nodes) {
        toon << "NODE;" << n.id << ";" << n.x << ";" << n.y << "\n";
    }
    for (const auto& e : edges) {
        toon << e << "\n";
    }
    toon << "NETWORK_END\n";

    return toon.str();
}