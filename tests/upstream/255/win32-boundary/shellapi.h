#pragma once
#include "windows.h"

// Named fields and flag values used by real trash_win.cpp. SHFileOperation is
// provided by the test, allowing its return code and abort bit to vary freely.
constexpr unsigned FO_DELETE = 0x0003;
constexpr unsigned short FOF_NOCONFIRMATION = 0x0010;
constexpr unsigned short FOF_ALLOWUNDO = 0x0040;
constexpr unsigned short FOF_SIMPLEPROGRESS = 0x0100;
constexpr unsigned short FOF_NOERRORUI = 0x0400;
constexpr unsigned short FOF_WANTNUKEWARNING = 0x4000;
struct SHFILEOPSTRUCT
{
    void *hwnd;
    unsigned wFunc;
    const wchar_t *pFrom;
    const wchar_t *pTo;
    unsigned short fFlags;
    BOOL fAnyOperationsAborted;
    void *hNameMappings;
    const wchar_t *lpszProgressTitle;
};
int SHFileOperation(SHFILEOPSTRUCT *operation);
