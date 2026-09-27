#define NOMINMAX
#include <windows.h>
#include <winhttp.h>
#include <shlobj.h>
#include <io.h>
#include <fcntl.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <regex>
#include <string>
#include "identity.hpp"
#pragma comment(lib,"winhttp.lib")
#pragma comment(lib,"shell32.lib")

// Chrome launches this short-lived internal process, never the desktop UI.
// The only capability it returns is the running user's current app session.
static std::string Connect() {
    wchar_t local[MAX_PATH];
    if (FAILED(SHGetFolderPathW(nullptr,CSIDL_LOCAL_APPDATA,nullptr,0,local))) return "{\"connected\":false}";
    std::ifstream f(std::filesystem::path(local)/L"MSXLiveBridge"/L"session.json");
    std::string text((std::istreambuf_iterator<char>(f)),{});
    if (text.size()>4096) return "{\"connected\":false}";
    std::smatch match;
    const auto field=[&](const char* name,const char* pattern) {
        if (!std::regex_search(text,match,std::regex(std::string("\"")+name+"\"\\s*:\\s*\"("+pattern+")\""))) return std::string();
        return match[1].str();
    };
    const std::string token=field("token","[A-Za-z0-9_-]{40,64}"),instance=field("instance","[a-f0-9]{32}");
    if (token.empty()||instance.empty()||!std::regex_search(text,std::regex("\"port\"\\s*:\\s*27183\\s*[,}]"))) return "{\"connected\":false}";
    HINTERNET session=WinHttpOpen(L"MSX LiveBridge",WINHTTP_ACCESS_TYPE_NO_PROXY,nullptr,nullptr,0);
    if (!session) return "{\"connected\":false}";
    WinHttpSetTimeouts(session,1000,1000,1000,1000);
    HINTERNET connection=WinHttpConnect(session,L"127.0.0.1",27183,0);
    HINTERNET request=connection?WinHttpOpenRequest(connection,L"GET",L"/session",nullptr,nullptr,nullptr,0):nullptr;
    bool ok=false;
    if (request) {
        DWORD disable=WINHTTP_DISABLE_REDIRECTS;WinHttpSetOption(request,WINHTTP_OPTION_DISABLE_FEATURE,&disable,sizeof(disable));
        std::wstring header=L"Authorization: Bearer "+std::wstring(token.begin(),token.end());
        if (WinHttpSendRequest(request,header.c_str(),static_cast<DWORD>(header.size()),nullptr,0,0,0)&&WinHttpReceiveResponse(request,nullptr)) {
            DWORD code=0,size=sizeof(code);
            if (WinHttpQueryHeaders(request,WINHTTP_QUERY_STATUS_CODE|WINHTTP_QUERY_FLAG_NUMBER,nullptr,&code,&size,nullptr)&&code==200) {
                std::string body;char buffer[1024];DWORD count=0;
                while (body.size()<4096 && WinHttpReadData(request,buffer,sizeof(buffer),&count)&&count) body.append(buffer,count);
                ok=body.find(instance)!=std::string::npos && body.find("MSX LiveBridge")!=std::string::npos;
            }
        }
        WinHttpCloseHandle(request);
    }
    if (connection) WinHttpCloseHandle(connection);WinHttpCloseHandle(session);
    return ok?"{\"connected\":true,\"port\":27183,\"token\":\""+token+"\",\"instance\":\""+instance+"\"}":"{\"connected\":false}";
}
int wmain(int argc,wchar_t** argv) {
    if (argc<2 || !IsAllowedExtensionOrigin(argv[1])) return 2;
    _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
    unsigned long size=0;
    std::cin.read(reinterpret_cast<char*>(&size),4);
    if (!std::cin || !size || size>8192) return 3;
    std::string request(size,'\0');std::cin.read(request.data(),size);
    if (!std::cin || !std::regex_search(request,std::regex("\"action\"\\s*:\\s*\"connect\""))) return 3;
    std::string response;
    try {response=Connect();} catch (...) {response="{\"connected\":false}";}
    size=static_cast<unsigned long>(response.size());
    std::cout.write(reinterpret_cast<const char*>(&size),4);std::cout.write(response.data(),size);std::cout.flush();return 0;
}
