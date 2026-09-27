#pragma once
#include <cstdint>
#include <string_view>
struct FtdiProfile { std::string_view name; uint32_t baud; uint8_t clock_width; uint8_t bit_mode_mask; bool verified; };
inline constexpr FtdiProfile kFtdiProfiles[] = {
  {"FT232H", 240000, 32, 0xff, true},   // FS-A1ST/VSIF: PSG, OPLL, SCC-I verified
  {"FT232R", 240000, 25, 0xff, false},  // MAmidiMEmo historical default; hardware unverified
  {"Custom", 240000, 32, 0xff, false},
};
