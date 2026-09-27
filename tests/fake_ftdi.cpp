// Test-only D2XX replacement. Never copied beside the production sender.
#include <windows.h>
#include <fstream>
#include <iomanip>
#include <cstdlib>
static int writes = 0;
static double queuedUntil = 0;
static double now() { LARGE_INTEGER q,f; QueryPerformanceCounter(&q); QueryPerformanceFrequency(&f); return double(q.QuadPart)/f.QuadPart; }
static int option(const char* key) { const char* value = std::getenv(key); return value ? std::atoi(value) : 0; }
static void lifecycle(const char* event) {
    const char* path=std::getenv("FAKE_LIFECYCLE"); if (!path) return;
    std::ofstream out(path,std::ios::app);
    out << "{\"event\":\"" << event << "\",\"pid\":" << GetCurrentProcessId() << "}\n";
}
#define API extern "C" __declspec(dllexport) unsigned long __stdcall
API FT_Open(int, void** handle) { *handle = reinterpret_cast<void*>(1); lifecycle("open"); return 0; }
API FT_Close(void*) { lifecycle("close"); return 0; }
API FT_SetBitMode(void*, unsigned char mask, unsigned char mode) { return (mode==0 && mask==0)||(mode==1 && mask==255) ? 0:1; }
API FT_SetBaudRate(void*, unsigned long value) { return value == static_cast<unsigned long>(option("FAKE_BAUD")?option("FAKE_BAUD"):240000) ? 0 : 1; }
API FT_SetTimeouts(void*, unsigned long a, unsigned long b) { return a == 500 && b == 500 ? 0 : 1; }
API FT_SetLatencyTimer(void*, unsigned char value) { return value == 0 ? 0 : 1; }
API FT_Write(void*, void* data, unsigned long size, unsigned long* written) {
    ++writes;
    const double started = now();
    Sleep(option("FAKE_WRITE_MS"));
    *written = size - (option("FAKE_SHORT_AT") == writes ? 1 : 0);
    queuedUntil = now() + option("FAKE_QUEUE_MS")/1000.0;
    std::ofstream out(std::getenv("FAKE_LOG"), std::ios::app);
    out << std::setprecision(17) << "{\"at\":" << started << ",\"hex\":\"";
    auto bytes = static_cast<unsigned char*>(data);
    for (unsigned long i=0; i<size; ++i) out << std::hex << std::setfill('0') << std::setw(2) << int(bytes[i]);
    out << "\"}\n";
    return 0;
}
API FT_GetStatus(void*, unsigned long* rx, unsigned long* tx, unsigned long* events) {
    *rx = *events = 0;
    *tx = option("FAKE_STUCK") || now() < queuedUntil ? 100 : 0;
    return option("FAKE_STATUS_ERROR");
}

API FT_OpenEx(void* serial, unsigned long flags, void** handle) {
    if (flags==4 && reinterpret_cast<uintptr_t>(serial)==19) return FT_Open(0,handle);
    if (flags!=1 || !serial || std::string(static_cast<char*>(serial))!="TEST123") return 2;
    return FT_Open(0,handle);
}
