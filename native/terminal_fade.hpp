#pragma once
#include <algorithm>
#include <cstdint>
#include <functional>

// PSG has no master gain for its hardware envelope. During the ending only,
// follow its envelope phase in software and map the instantaneous level to
// the fixed-volume ladder. Normal playback retains the hardware envelope.
struct PsgEnvelope {
    int low=0, high=0, shape=0, pointer=0, sample=0;
    bool up=false, held=true;
    double count=0;
    void advance(int at) {
        const double ticks=std::max(0,at-sample)*(3579545.0/2/8/44100);
        sample=at;
        const int period=std::max(1,low+(high<<8));
        const double total=count+ticks;
        auto steps=static_cast<uint64_t>(total/period);
        count=std::fmod(total,period);
        if (held) return;
        if ((shape&8) && !(shape&1)) steps%=64;
        else steps=std::min<uint64_t>(steps,64);
        while (steps-- && !held) {
            pointer+=up?1:-1;
            if (pointer<0 || pointer>31) {
                if (!(shape&8)) {pointer=0;held=true;}
                else {
                    if (((shape>>1)^shape)&1) up=!up;
                    held=(shape&1)!=0;pointer=up?0:31;
                }
            }
        }
    }
    void write(int address, int data, int at) {
        advance(at);
        if (address==11) low=data;
        if (address==12) high=data;
        if (address==13) {shape=data&15;up=(shape&4)!=0;pointer=up?0:31;held=false;}
    }
    int level(int at) {advance(at);return pointer/2;}
};

class TerminalFade {
    std::filesystem::path path;
    bool loaded=false;
    int start=0, end=0, rate=44100;
    uint64_t step=0;
    double nextRead=0;
    std::map<int,std::map<int,unsigned char>> lastLevels;
public:
    PsgEnvelope envelope;
    explicit TerminalFade(std::filesystem::path statusPath):path(std::move(statusPath)) {
        path.replace_extension(L".ending.json");
    }
    void read(double now) {
        if (loaded || now<nextRead) return;
        nextRead=now+.1;
        std::ifstream input(path); if (!input) return;
        const std::string data((std::istreambuf_iterator<char>(input)),{});
        const auto number=[&](const char* key)->int {
            std::smatch match;
            if (!std::regex_search(data,match,std::regex(std::string("\"")+key+"\":([0-9]+)")))
                throw std::runtime_error("invalid ending metadata");
            return std::stoi(match[1]);
        };
        start=number("start_sample");end=number("end_sample");rate=number("rate");step=number("step");
        if (end<start || rate<8000 || rate>192000) throw std::runtime_error("invalid fade range");
        loaded=true;
    }
    bool active(int sample) const {return loaded && step && sample>=start;}
    bool ended(int sample) const {return loaded && sample>=end;}
    double gain(int sample) const {
        if (!active(sample)) return 1;
        const auto frames=static_cast<uint64_t>(std::max(0,sample-start))*rate/44100+1;
        const uint64_t remaining=frames*step>=(1ull<<31)?0:(1ull<<31)-frames*step;
        return static_cast<double>(remaining>>23)/256;
    }
    // AY/MSX PSG is logarithmic, SCC-I is linear, OPLL is attenuation in 3 dB units.
    static int psgLevel(int original,double gain) {
        static constexpr int amplitude[16]={0,3,4,6,9,13,18,29,34,55,77,98,130,166,208,255};
        const double target=amplitude[original&15]*gain;
        int result=0;
        for (int i=1;i<=original;++i)
            if (std::abs(amplitude[i]-target)<std::abs(amplitude[result]-target)) result=i;
        return result;
    }
    static int opllLevel(int original,double gain) {
        if (gain<=0) return 15;
        const int attenuation=static_cast<int>(std::lround(-20*std::log10(gain)/3.0));
        return std::min(15,(original&15)+attenuation);
    }
    int value(int type,int address,int data,const MusicState& music,int sample) {
        const double g=gain(sample);
        if (!active(sample)) return data;
        if (type==0x17 && address>=8 && address<=10)
            return psgLevel((data&16)?envelope.level(sample):data&15,g);
        if (type==4 && address>=0xaa && address<=0xae)
            return static_cast<int>(std::lround((data&15)*g));
        if (type==1 && address>=0x30 && address<=0x38) {
            const auto chip=music.registers.find(1);
            const bool rhythm=chip!=music.registers.end() && chip->second.contains(0x0e) && (chip->second.at(0x0e)&32);
            const int high=rhythm && address>=0x37 ? opllLevel(data>>4,g)<<4 : data&0xf0;
            return high|opllLevel(data&15,g);
        }
        return data;
    }
    std::vector<unsigned char> levels(const MusicState& music,int sample,bool force=false) {
        std::vector<unsigned char> out;
        if (!active(sample)) return out;
        for (const auto& [type,registers]:music.registers) for (const auto& [address,data]:registers) {
            if (!((type==0x17 && address>=8 && address<=10) || (type==1 && address>=0x30 && address<=0x38)
                || (type==4 && address>=0xaa && address<=0xae))) continue;
            const auto level=static_cast<unsigned char>(value(type,address,data,music,sample));
            if (force || !lastLevels[type].contains(address) || lastLevels[type][address]!=level) {
                AddFrame(out,static_cast<unsigned char>(type),static_cast<unsigned char>(address),level);
                lastLevels[type][address]=level;
            }
        }
        return out;
    }
    // After fading only: silence rhythm triggers as well as the normal stop frames.
    static std::vector<unsigned char> finalMute() {
        std::vector<unsigned char> out;
        for (unsigned char a=8;a<=10;++a) AddFrame(out,0x17,a,0);
        for (unsigned char a=0xaa;a<=0xae;++a) AddFrame(out,4,a,0);
        AddFrame(out,1,0x0e,0);
        return out;
    }
};
