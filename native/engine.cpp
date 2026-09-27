#include "ftdi_profiles.hpp"
#define NOMINMAX
#include <windows.h>
#include <iostream>
#include <fstream>
#include <filesystem>
#include <map>
#include <regex>
#include <string>
#include <vector>
#include <cmath>
#include <stdexcept>
#include <functional>

using FT_HANDLE = void*;
using FT_STATUS = unsigned long;
using OpenFn = FT_STATUS(__stdcall*)(int, FT_HANDLE*);
using CloseFn = FT_STATUS(__stdcall*)(FT_HANDLE);
using BitFn = FT_STATUS(__stdcall*)(FT_HANDLE, unsigned char, unsigned char);
using BaudFn = FT_STATUS(__stdcall*)(FT_HANDLE, unsigned long);
using TimeoutFn = FT_STATUS(__stdcall*)(FT_HANDLE, unsigned long, unsigned long);
using LatencyFn = FT_STATUS(__stdcall*)(FT_HANDLE, unsigned char);
using WriteFn = FT_STATUS(__stdcall*)(FT_HANDLE, void*, unsigned long, unsigned long*);
using StatusFn = FT_STATUS(__stdcall*)(FT_HANDLE, unsigned long*, unsigned long*, unsigned long*);

static std::vector<unsigned char> Expand(const std::vector<unsigned char>& logical, unsigned char width) {
    std::vector<unsigned char> physical;
    physical.reserve(logical.size() * width);
    for (auto byte : logical) for (unsigned int i = 0; i < width; ++i) physical.push_back(byte);
    return physical;
}

static void AddFrame(std::vector<unsigned char>& output, unsigned char type, unsigned char address, unsigned char data) {
    output.push_back(static_cast<unsigned char>(0x20 | type));
    output.push_back(static_cast<unsigned char>(address >> 4));
    output.push_back(static_cast<unsigned char>(0x10 | (address & 0x0f)));
    output.push_back(static_cast<unsigned char>(data >> 4));
    output.push_back(static_cast<unsigned char>(0x10 | (data & 0x0f)));
}

static std::vector<unsigned char> BuildStopFrames() {
    std::vector<unsigned char> stop = {0x37,0x00,0x16,0x00,0x10, 0x37,0x00,0x17,0x0b,0x1f,
        0x37,0x00,0x18,0x00,0x10, 0x37,0x00,0x19,0x00,0x10, 0x37,0x00,0x1a,0x00,0x10};
    for (unsigned char address = 0x20; address <= 0x28; ++address) AddFrame(stop, 1, address, 0);
    for (unsigned char address = 0xaa; address <= 0xaf; ++address) AddFrame(stop, 4, address, 0);
    return stop;
}

struct TimedBatch { int bin; int sample; std::vector<unsigned char> bytes; };

static std::vector<unsigned char> ParseHex(const std::string& hex) {
    std::vector<unsigned char> bytes;
    if ((hex.size() & 1) != 0) return {};
    bytes.reserve(hex.size() / 2);
    for (size_t i = 0; i < hex.size(); i += 2) bytes.push_back(static_cast<unsigned char>(std::stoul(hex.substr(i, 2), nullptr, 16)));
    return bytes;
}

static std::vector<TimedBatch> LoadBatches(const std::filesystem::path& path) {
    std::ifstream input(path);
    std::vector<TimedBatch> batches;
    const std::regex pattern(R"vsif("bin":(-?[0-9]+),"sample":([0-9]+),"hex":"([0-9a-fA-F]*)")vsif");
    for (std::string line; std::getline(input, line);) {
        std::smatch match;
        if (std::regex_search(line, match, pattern)) batches.push_back({std::stoi(match[1]), std::stoi(match[2]), ParseHex(match[3])});
    }
    return batches;
}

// Keep the state represented by music frames already delivered to the ROM.
// A pause first mutes the chips, then a resume restores this state without
// advancing the music clock.  The 0x20 form is the VSIF compressed form: its
// data byte belongs to the previous type at the next register address.
struct MusicState {
    std::map<int, std::map<int, unsigned char>> registers;
    int lastType = -1;
    int lastAddress = -1;

    void apply(const std::vector<unsigned char>& bytes,
               const std::function<void(int,int,unsigned char)>& visit = {}) {
        for (size_t i = 0; i < bytes.size();) {
            const unsigned char header = bytes[i];
            if (header == 0x20 && lastType >= 0 && i + 2 < bytes.size()) {
                const int address = lastAddress + 1;
                const unsigned char data = static_cast<unsigned char>((bytes[i + 1] << 4) | (bytes[i + 2] & 0x0f));
                registers[lastType][address] = data;
                lastAddress = address;
                if (visit) visit(lastType,address,data);
                i += 3;
            } else if ((header & 0xe0) == 0x20 && header != 0x20 && i + 4 < bytes.size()) {
                const int type = header & 0x1f;
                const int address = (bytes[i + 1] << 4) | (bytes[i + 2] & 0x0f);
                const unsigned char data = static_cast<unsigned char>((bytes[i + 3] << 4) | (bytes[i + 4] & 0x0f));
                registers[type][address] = data;
                lastType = type;
                lastAddress = address;
                if (visit) visit(type,address,data);
                i += 5;
            } else {
                ++i;
            }
        }
    }

    std::vector<unsigned char> resumeFrames() const {
        std::vector<unsigned char> output;
        const auto append = [&](int type, int address) {
            const auto typeIt = registers.find(type);
            if (typeIt == registers.end()) return;
            const auto valueIt = typeIt->second.find(address);
            if (valueIt != typeIt->second.end()) AddFrame(output, static_cast<unsigned char>(type), static_cast<unsigned char>(address), valueIt->second);
        };
        // PSG: program periods/mixer/envelope first, then make channels audible.
        for (int address = 0; address <= 13; ++address) if (address < 8 || address > 10) append(0x17, address);
        for (int address = 8; address <= 10; ++address) append(0x17, address);
        // OPLL: restore parameters before the channel key-on registers.
        for (int address = 0; address <= 0x3f; ++address) if (address < 0x20 || address > 0x28) append(1, address);
        for (int address = 0x20; address <= 0x28; ++address) append(1, address);
        // SCC-I: reselect it, restore waveform/frequency state, then volumes/key.
        if (registers.contains(4)) {
            AddFrame(output, 3, 1, 0); output.insert(output.end(), 4, 0);
            for (const auto& [address, value] : registers.at(4)) if (address < 0xaa || address > 0xaf) AddFrame(output, 4, static_cast<unsigned char>(address), value);
            for (int address = 0xaa; address <= 0xaf; ++address) append(4, address);
        }
        return output;
    }
};

#include "terminal_fade.hpp"

static double QpcSeconds() {
    LARGE_INTEGER q, f; QueryPerformanceCounter(&q); QueryPerformanceFrequency(&f);
    return static_cast<double>(q.QuadPart)/f.QuadPart;
}

static void PublishState(const std::filesystem::path& path, const char* state, int sample) {
    const auto temp = path.wstring()+L".tmp";
    { std::ofstream out(temp); out << "{\"state\":\"" << state << "\",\"sample\":" << sample << "}\n"; }
    for (int attempt=0; attempt<50; ++attempt) {
        if (MoveFileExW(temp.c_str(),path.c_str(),MOVEFILE_REPLACE_EXISTING)) return;
        Sleep(2);
    }
    throw std::runtime_error("cannot publish Native state");
}

int main(int argc, char** argv) {
    if (argc==2 && std::string(argv[1])=="--version") {
        std::cout << "MSX LiveBridge Engine 1.0.4\n"; return 0;
    }
    if (argc<6 || std::string(argv[2])!="play") {
        std::cerr << "usage: msx-vsif-sender PROFILE play BATCHES CONTROL STATUS\n"; return 2;
    }
    const FtdiProfile* profile=nullptr;
    for (const auto& candidate:kFtdiProfiles) if (candidate.name==argv[1]) profile=&candidate;
    if (!profile) { std::cerr << "unknown FTDI profile\n"; return 3; }
    FtdiProfile configured=*profile;
    std::string serial;
    DWORD ownerPid=0;
    DWORD location=0;
    bool customBaud=false,customWidth=false;
    try {
        for (int i=6;i<argc;i+=2) {
            if (i+1>=argc) return 3;
            const std::string key=argv[i],value=argv[i+1];
            if (key=="--device") { serial=value;if (serial.empty()||serial.size()>15) return 3; }
            else if (key=="--location") {location=std::stoul(value);if(!location) return 3;}
            else if (key=="--owner") ownerPid=std::stoul(value);
            else if (key=="--baud") {
                const auto baudValue=std::stoul(value);if (baudValue<300||baudValue>3000000) return 3;
                if (configured.name!="Custom" && baudValue!=configured.baud) return 3;
                configured.baud=baudValue;customBaud=true;
            } else if (key=="--width") {
                const auto widthValue=std::stoul(value);if (!widthValue||widthValue>255) return 3;
                if (configured.name!="Custom" && widthValue!=configured.clock_width) return 3;
                configured.clock_width=static_cast<uint8_t>(widthValue);customWidth=true;
            } else return 3;
        }
    } catch (...) {return 3;}
    if (location && !serial.empty()) return 3;
    if (configured.name=="Custom" && (!customBaud||!customWidth)) return 3;
    profile=&configured;
    struct OwnerWatch {
        HANDLE handle=nullptr;
        HANDLE done=nullptr, thread=nullptr;
        static DWORD WINAPI Watch(void* context) {
            auto& self=*static_cast<OwnerWatch*>(context);
            HANDLE waits[]={self.done,self.handle};
            if (WaitForMultipleObjects(2,waits,FALSE,INFINITE)==WAIT_OBJECT_0+1) {
                // Main loop normally mutes/closes on owner loss. A stuck D2XX
                // call cannot poll that loop; bound this fallback independently.
                if (WaitForSingleObject(self.done,5000)==WAIT_TIMEOUT)
                    TerminateProcess(GetCurrentProcess(),11);
            }
            return 0;
        }
        bool start() {
            done=CreateEventW(nullptr,TRUE,FALSE,nullptr);
            if (!done) return false;
            thread=CreateThread(nullptr,0,Watch,this,0,nullptr);
            return thread!=nullptr;
        }
        ~OwnerWatch() {
            if(done) SetEvent(done);
            if(thread) {WaitForSingleObject(thread,INFINITE);CloseHandle(thread);}
            if(done) CloseHandle(done);
            if(handle) CloseHandle(handle);
        }
    } owner;
    if (ownerPid) {owner.handle=OpenProcess(SYNCHRONIZE,FALSE,ownerPid);if(!owner.handle || !owner.start()) return 3;}

    const std::filesystem::path controlPath=argv[4], statusPath=argv[5];
    std::vector<TimedBatch> batches;
    try { batches=LoadBatches(argv[3]); }
    catch (const std::exception& e) { std::cerr << e.what(); return 4; }
    if (batches.empty() || (batches[0].bin!=-1 && batches[0].bin!=-2)) return 4;
    const bool snapshot=batches[0].bin==-2;
    if (snapshot && (batches.size()<2 || batches[1].bin!=-3)) return 4;
    const int base=snapshot ? batches[0].sample : 0;
#ifdef MSXLB_TEST
    HMODULE dll=LoadLibraryW(L"ftd2xx.dll");
#else
    HMODULE dll=LoadLibraryExW(L"ftd2xx.dll",nullptr,LOAD_LIBRARY_SEARCH_SYSTEM32);
#endif
    if (!dll) { std::cerr << "ftd2xx.dll not found\n"; return 5; }
    const auto open=reinterpret_cast<OpenFn>(GetProcAddress(dll,"FT_Open"));
    const auto close=reinterpret_cast<CloseFn>(GetProcAddress(dll,"FT_Close"));
    const auto bitMode=reinterpret_cast<BitFn>(GetProcAddress(dll,"FT_SetBitMode"));
    const auto baud=reinterpret_cast<BaudFn>(GetProcAddress(dll,"FT_SetBaudRate"));
    const auto timeouts=reinterpret_cast<TimeoutFn>(GetProcAddress(dll,"FT_SetTimeouts"));
    const auto latency=reinterpret_cast<LatencyFn>(GetProcAddress(dll,"FT_SetLatencyTimer"));
    const auto write=reinterpret_cast<WriteFn>(GetProcAddress(dll,"FT_Write"));
    const auto status=reinterpret_cast<StatusFn>(GetProcAddress(dll,"FT_GetStatus"));
    if (!open||!close||!bitMode||!baud||!timeouts||!latency||!write||!status) return 6;
    FT_HANDLE handle=nullptr;
    if (serial.empty() && !location) { if (open(0,&handle)) return 7; }
    else {
        using OpenExFn=FT_STATUS(__stdcall*)(void*,DWORD,FT_HANDLE*);
        const auto openEx=reinterpret_cast<OpenExFn>(GetProcAddress(dll,"FT_OpenEx"));
        void* address=location?reinterpret_cast<void*>(static_cast<uintptr_t>(location)):serial.data();
        if (!openEx || openEx(address,location?4:1,&handle)) return 7;
    }
    const auto send=[&](const std::vector<unsigned char>& bytes) {
        if (bytes.empty()) return true;
        auto physical=Expand(bytes,profile->clock_width);
        unsigned long written=0;
        return !write(handle,physical.data(),static_cast<unsigned long>(physical.size()),&written) && written==physical.size();
    };
    const auto requireSend=[&](const std::vector<unsigned char>& bytes) {
        if (!send(bytes)) throw std::runtime_error("FT_Write failed or short write");
    };
    std::string lastControl="stop";
    double unavailableSince=0;
    const auto control=[&]() {
        if (owner.handle && WaitForSingleObject(owner.handle,0)!=WAIT_TIMEOUT) return std::string("stop");
        HANDLE f=CreateFileW(controlPath.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
                             nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        if (f==INVALID_HANDLE_VALUE) {
            if (!unavailableSince) unavailableSince=QpcSeconds();
            return QpcSeconds()-unavailableSince<.05 ? lastControl : std::string("stop");
        }
        char buffer[32]={}; DWORD count=0;
        const bool ok=ReadFile(f,buffer,sizeof(buffer)-1,&count,nullptr)!=0; CloseHandle(f);
        std::string value(buffer,count); value=value.substr(0,value.find_first_of("\r\n"));
        if (!ok || (value!="run" && value!="pause" && value!="stop")) return std::string("stop");
        unavailableSince=0; lastControl=value; return value;
    };
    // Drain is a transport safety check, never a timing correction or browser clock input.
    const auto drain=[&]() {
        const double deadline=QpcSeconds()+2;
        for (;;) {
            unsigned long rx=0,tx=0,events=0;
            if (status(handle,&rx,&tx,&events)) throw std::runtime_error("FT_GetStatus failed");
            if (!tx) return;
            if (QpcSeconds()>deadline) throw std::runtime_error("TX drain timeout");
            Sleep(1);
        }
    };
    int sample=base, result=0;
    bool naturalFadeCompleted=false;
    try {
        if (bitMode(handle,0,0)||bitMode(handle,profile->bit_mode_mask,1)||baud(handle,profile->baud)
            ||timeouts(handle,500,500)||latency(handle,0)) throw std::runtime_error("FTDI setup failed");
        PublishState(statusPath,"preparing",sample);
        if (control()!="stop") {
            std::vector<unsigned char> silence;
            AddFrame(silence, 3, 1, 0); silence.insert(silence.end(), 4, 0);
            AddFrame(silence, 0x17, 6, 0); AddFrame(silence, 0x17, 7, 0x3f);
            AddFrame(silence, 0x17, 8, 0); AddFrame(silence, 0x17, 9, 0); AddFrame(silence, 0x17, 10, 0);
            AddFrame(silence, 1, 0x0e, 0);
            for (unsigned char address = 0x20; address <= 0x28; ++address) AddFrame(silence, 1, address, 0);
            for (unsigned char address = 0x30; address <= 0x38; ++address) AddFrame(silence, 1, address, 0xff);
            for (unsigned char address = 0xaa; address <= 0xaf; ++address) AddFrame(silence, 4, address, 0);

            requireSend(silence);
            MusicState music;
            TerminalFade fade(statusPath);
            const auto observe=[&](int type,int address,unsigned char data) {
                if (type==0x17) fade.envelope.write(address,data,sample);
            };
            const auto deliverMusic=[&](const std::vector<unsigned char>& bytes) {
                if (!fade.active(sample)) {
                    requireSend(bytes); music.apply(bytes,observe); return;
                }
                std::vector<unsigned char> output;
                music.apply(bytes,[&](int type,int address,unsigned char data) {
                    observe(type,address,data);
                    AddFrame(output,static_cast<unsigned char>(type),static_cast<unsigned char>(address),
                        static_cast<unsigned char>(fade.value(type,address,data,music,sample)));
                    if (type==3) output.insert(output.end(),4,0);
                });
                requireSend(output);
            };
            const auto restoreMusic=[&]() {
                const auto frames=music.resumeFrames();
                if (!fade.active(sample)) {requireSend(frames);return;}
                MusicState restored=music;
                std::vector<unsigned char> output;
                restored.apply(frames,[&](int type,int address,unsigned char data) {
                    AddFrame(output,static_cast<unsigned char>(type),static_cast<unsigned char>(address),
                        static_cast<unsigned char>(fade.value(type,address,data,restored,sample)));
                    if (type==3) output.insert(output.end(),4,0);
                });
                requireSend(output);
            };
            deliverMusic(batches[0].bytes);
            drain();
            const double readyAt=QpcSeconds()+.5;
            while (QpcSeconds()<readyAt && control()!="stop") Sleep(1);
            fade.read(QpcSeconds());
            size_t next=snapshot ? 2 : 1;
            if (snapshot) music.apply(batches[1].bytes);
            bool paused=control()=="pause", cursorInterrupted=false;
            if (control()!="stop" && !paused && snapshot && !fade.ended(sample)) deliverMusic(batches[1].bytes);
            if (paused) requireSend(BuildStopFrames());
            double origin=QpcSeconds(), nextReport=0;
            int nextFadeSample=base;
            bool fadingReported=false;
            if (control()!="stop") PublishState(statusPath,paused?"paused":"playing",sample);
            while (next<batches.size()) {
                fade.read(QpcSeconds());
                const auto request=control();
                if (request=="stop") break;
                if (request=="pause" && !paused) {
                    sample=base+static_cast<int>((QpcSeconds()-origin)*44100);
                    requireSend(BuildStopFrames()); paused=true;
                    PublishState(statusPath,"paused",sample);
                } else if (request=="run" && paused) {
                    restoreMusic(); drain();
                    // Restoring hardware state must not advance the music clock.
                    origin=QpcSeconds()-(sample-base)/44100.0; paused=false; cursorInterrupted=true;
                    PublishState(statusPath,"playing",sample);
                }
                if (paused) { Sleep(1); continue; }
                sample=base+static_cast<int>((QpcSeconds()-origin)*44100);
                if (fade.ended(sample)) {
                    naturalFadeCompleted=fade.active(sample) && control()=="run";
                    if (naturalFadeCompleted) {
                        requireSend(fade.levels(music,sample,true));
                        std::cout << "fade-complete sample=" << sample << "\n";
                    }
                    break;
                }
                if (sample>=batches[next].sample) {
                    // Submit already-due writes together, preserving source order.
                    // Never pull a future register/waveform update into this send.
                    std::vector<unsigned char> bytes;
                    do {
                        const auto& due=batches[next++].bytes;
                        bytes.insert(bytes.end(),due.begin(),due.end());
                    } while (next<batches.size() && batches[next].sample<=sample);
                    // Mute/restore changes the ROM's compression cursor. Expand the
                    // first continuation after resume using the retained music cursor.
                    if (cursorInterrupted && bytes.size()>=3 && bytes[0]==0x20 && music.lastType>=0) {
                        std::vector<unsigned char> expanded;
                        AddFrame(expanded,static_cast<unsigned char>(music.lastType),
                            static_cast<unsigned char>(music.lastAddress+1),
                            static_cast<unsigned char>((bytes[1]<<4)|(bytes[2]&15)));
                        expanded.insert(expanded.end(),bytes.begin()+3,bytes.end()); bytes=std::move(expanded);
                    }
                    if (!bytes.empty()) { deliverMusic(bytes); cursorInterrupted=false; }
                } else Sleep(1);
                if (fade.active(sample) && sample>=nextFadeSample) {
                    if (!fadingReported) {std::cout << "fade-start sample=" << sample << "\n";fadingReported=true;}
                    const auto levels=fade.levels(music,sample);
                    if (!levels.empty()) {requireSend(levels);cursorInterrupted=true;}
                    nextFadeSample=sample+882;
                }
                if (QpcSeconds()>=nextReport) {
                    PublishState(statusPath,fade.active(sample)?"fading":"playing",sample); nextReport=QpcSeconds()+.1;
                }
            }
        }
    } catch (const std::exception& error) { std::cerr << error.what() << "\n"; result=9; }
    if (naturalFadeCompleted && !send(TerminalFade::finalMute())) result=10;
    // Always attempt the verified mute and wait before bit-bang RESET, even on failure.
    if (!send(BuildStopFrames())) result=10;
    Sleep(50); bitMode(handle,0,0); close(handle); FreeLibrary(dll);
    try { PublishState(statusPath,result?"error":"stopped",sample); }
    catch (const std::exception& error) { std::cerr << error.what(); result=11; }
    return result;
}
