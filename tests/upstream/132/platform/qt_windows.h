// SPDX-License-Identifier: GPL-3.0-only
// Linux harness only: appearance.h's Windows stock-font query is unavailable.
// Do not emulate Windows fonts or claim to validate Windows appearance here.
#pragma once
struct LOGFONTW {
    wchar_t lfFaceName[32];
    int lfHeight, lfWeight;
    unsigned char lfItalic, lfUnderline, lfStrikeOut;
};
constexpr int DEFAULT_GUI_FONT = 17;
inline void *GetStockObject(int) { return nullptr; }
inline int GetObjectW(void *, int, void *) { return 0; }
inline unsigned int GetDpiForSystem() { return 96; }
