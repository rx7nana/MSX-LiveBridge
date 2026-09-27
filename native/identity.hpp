#pragma once
#include <string_view>
inline constexpr std::wstring_view kExtensionOrigins[] = {
    L"chrome-extension://fcebnajmcgjhmkbgefjgaaadnjpdamnc/", // unpacked development build
    L"chrome-extension://cfkcbmejlakciepflheboofnphdkoghf/", // Chrome Web Store
};
inline bool IsAllowedExtensionOrigin(std::wstring_view origin) {
    for (auto allowed : kExtensionOrigins) if (origin == allowed) return true;
    return false;
}
