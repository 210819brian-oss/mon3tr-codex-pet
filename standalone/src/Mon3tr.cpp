#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <windowsx.h>
#include <objidl.h>
#include <gdiplus.h>
#include <mmsystem.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <limits>
#include <string>
#include <vector>

#pragma comment(lib, "gdiplus.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "winmm.lib")

namespace {
constexpr int kWidth = 256;
constexpr int kHeight = 277;
constexpr int kWalkFrames = 64;
constexpr int kIdleFrames = 6;
constexpr int kExitCommand = 1001;
constexpr double kPixelsPerPose = 4.0; // one stride cycle per 256 horizontal pixels
constexpr double kStopSeconds = 0.075;

struct Frame {
    std::vector<std::uint8_t> bgra;
};

std::vector<Frame> gWalkRight;
std::vector<Frame> gWalkLeft;
std::vector<Frame> gIdle;
const Frame* gCurrentFrame = nullptr;
HWND gWindow = nullptr;
HDC gScreenDc = nullptr;
HDC gMemoryDc = nullptr;
HBITMAP gDib = nullptr;
HGDIOBJ gOldBitmap = nullptr;
void* gDibBits = nullptr;
int gWindowX = 0;
int gWindowY = 0;
int gGrabX = 0;
int gGrabY = 0;
int gLastCursorX = 0;
bool gDragging = false;
bool gMovingLeft = false;
bool gRunning = true;
double gWalkPhase = 0.0;
double gLastHorizontalMove = -100.0;
double gIdleStart = 0.0;
int gPresentedX = std::numeric_limits<int>::min();
int gPresentedY = std::numeric_limits<int>::min();
LARGE_INTEGER gFrequency{};
LARGE_INTEGER gOrigin{};

double NowSeconds() {
    LARGE_INTEGER value{};
    QueryPerformanceCounter(&value);
    return static_cast<double>(value.QuadPart - gOrigin.QuadPart)
           / static_cast<double>(gFrequency.QuadPart);
}

std::filesystem::path ExecutableDirectory() {
    std::array<wchar_t, 32768> path{};
    const DWORD length = GetModuleFileNameW(nullptr, path.data(),
                                             static_cast<DWORD>(path.size()));
    return std::filesystem::path(std::wstring(path.data(), length)).parent_path();
}

bool LoadSheet(const std::filesystem::path& path, int columns, int rows,
               std::vector<Frame>& frames) {
    Gdiplus::Bitmap bitmap(path.c_str());
    if (bitmap.GetLastStatus() != Gdiplus::Ok ||
        bitmap.GetWidth() != static_cast<UINT>(columns * kWidth) ||
        bitmap.GetHeight() != static_cast<UINT>(rows * kHeight)) {
        return false;
    }

    Gdiplus::Rect rect(0, 0, columns * kWidth, rows * kHeight);
    Gdiplus::BitmapData data{};
    if (bitmap.LockBits(&rect, Gdiplus::ImageLockModeRead,
                        PixelFormat32bppARGB, &data) != Gdiplus::Ok) {
        return false;
    }
    const auto* base = static_cast<const std::uint8_t*>(data.Scan0);
    frames.clear();
    frames.resize(columns * rows);
    for (int index = 0; index < columns * rows; ++index) {
        Frame& frame = frames[index];
        frame.bgra.resize(kWidth * kHeight * 4);
        const int sourceX = (index % columns) * kWidth;
        const int sourceY = (index / columns) * kHeight;
        for (int y = 0; y < kHeight; ++y) {
            const auto* source = base + (sourceY + y) * data.Stride
                                 + sourceX * 4;
            auto* target = frame.bgra.data() + y * kWidth * 4;
            for (int x = 0; x < kWidth; ++x) {
                const unsigned alpha = source[x * 4 + 3];
                target[x * 4 + 0] = static_cast<std::uint8_t>(
                    (source[x * 4 + 0] * alpha + 127) / 255);
                target[x * 4 + 1] = static_cast<std::uint8_t>(
                    (source[x * 4 + 1] * alpha + 127) / 255);
                target[x * 4 + 2] = static_cast<std::uint8_t>(
                    (source[x * 4 + 2] * alpha + 127) / 255);
                target[x * 4 + 3] = static_cast<std::uint8_t>(alpha);
            }
        }
    }
    bitmap.UnlockBits(&data);
    return true;
}

void MirrorWalk() {
    gWalkLeft.resize(gWalkRight.size());
    for (std::size_t index = 0; index < gWalkRight.size(); ++index) {
        auto& left = gWalkLeft[index].bgra;
        const auto& right = gWalkRight[index].bgra;
        left.resize(right.size());
        for (int y = 0; y < kHeight; ++y) {
            for (int x = 0; x < kWidth; ++x) {
                std::memcpy(left.data() + (y * kWidth + x) * 4,
                            right.data() + (y * kWidth + kWidth - 1 - x) * 4,
                            4);
            }
        }
    }
}

bool CreateLayerBuffer() {
    gScreenDc = GetDC(nullptr);
    gMemoryDc = CreateCompatibleDC(gScreenDc);
    BITMAPINFO bitmapInfo{};
    bitmapInfo.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    bitmapInfo.bmiHeader.biWidth = kWidth;
    bitmapInfo.bmiHeader.biHeight = -kHeight; // top-down BGRA
    bitmapInfo.bmiHeader.biPlanes = 1;
    bitmapInfo.bmiHeader.biBitCount = 32;
    bitmapInfo.bmiHeader.biCompression = BI_RGB;
    gDib = CreateDIBSection(gScreenDc, &bitmapInfo, DIB_RGB_COLORS,
                            &gDibBits, nullptr, 0);
    if (!gScreenDc || !gMemoryDc || !gDib || !gDibBits) return false;
    gOldBitmap = SelectObject(gMemoryDc, gDib);
    return true;
}

void DestroyLayerBuffer() {
    if (gMemoryDc && gOldBitmap) SelectObject(gMemoryDc, gOldBitmap);
    if (gDib) DeleteObject(gDib);
    if (gMemoryDc) DeleteDC(gMemoryDc);
    if (gScreenDc) ReleaseDC(nullptr, gScreenDc);
}

bool Present(const Frame& frame) {
    if (gCurrentFrame == &frame && gWindowX == gPresentedX &&
        gWindowY == gPresentedY) {
        return true;
    }
    if (gCurrentFrame != &frame) {
        std::memcpy(gDibBits, frame.bgra.data(), frame.bgra.size());
    }
    POINT destination{gWindowX, gWindowY};
    POINT source{0, 0};
    SIZE size{kWidth, kHeight};
    BLENDFUNCTION blend{AC_SRC_OVER, 0, 255, AC_SRC_ALPHA};
    if (!UpdateLayeredWindow(gWindow, gScreenDc, &destination, &size,
                             gMemoryDc, &source, 0, &blend, ULW_ALPHA)) {
        return false;
    }
    gCurrentFrame = &frame;
    gPresentedX = gWindowX;
    gPresentedY = gWindowY;
    return true;
}

double FrameInterval() {
    MONITORINFOEXW info{};
    info.cbSize = sizeof(info);
    DEVMODEW display{};
    display.dmSize = sizeof(display);
    const HMONITOR monitor = MonitorFromWindow(gWindow, MONITOR_DEFAULTTONEAREST);
    const int refresh = GetMonitorInfoW(monitor, &info) &&
                        EnumDisplaySettingsW(info.szDevice, ENUM_CURRENT_SETTINGS,
                                             &display) &&
                        display.dmDisplayFrequency >= 30
                        ? static_cast<int>(display.dmDisplayFrequency) : 60;
    return 1.0 / std::clamp(refresh, 60, 240);
}

int IdleIndex(double now) {
    constexpr std::array<double, kIdleFrames> durations{
        0.28, 0.11, 0.11, 0.14, 0.14, 0.32};
    constexpr double total = 1.10;
    double phase = std::fmod(std::max(0.0, now - gIdleStart), total);
    for (int index = 0; index < kIdleFrames; ++index) {
        if (phase < durations[index]) return index;
        phase -= durations[index];
    }
    return 0;
}

void Tick(double now) {
    bool walking = false;
    if (gDragging) {
        POINT cursor{};
        GetCursorPos(&cursor);
        const int virtualLeft = GetSystemMetrics(SM_XVIRTUALSCREEN);
        const int virtualTop = GetSystemMetrics(SM_YVIRTUALSCREEN);
        const int virtualRight = virtualLeft + GetSystemMetrics(SM_CXVIRTUALSCREEN);
        const int virtualBottom = virtualTop + GetSystemMetrics(SM_CYVIRTUALSCREEN);
        gWindowX = std::clamp(static_cast<int>(cursor.x) - gGrabX,
                              virtualLeft - kWidth + 24,
                              virtualRight - 24);
        gWindowY = std::clamp(static_cast<int>(cursor.y) - gGrabY,
                              virtualTop - kHeight + 24,
                              virtualBottom - 24);
        const int dx = cursor.x - gLastCursorX;
        if (dx != 0) {
            gWalkPhase += static_cast<double>(std::abs(dx)) / kPixelsPerPose;
            gWalkPhase = std::fmod(gWalkPhase, static_cast<double>(kWalkFrames));
            gMovingLeft = dx < 0;
            gLastHorizontalMove = now;
        }
        gLastCursorX = cursor.x;
        walking = (now - gLastHorizontalMove) < kStopSeconds;
    }
    if (walking) {
        const int index = static_cast<int>(gWalkPhase) % kWalkFrames;
        Present(gMovingLeft ? gWalkLeft[index] : gWalkRight[index]);
    } else {
        Present(gIdle[IdleIndex(now)]);
    }
}

LRESULT CALLBACK WindowProcedure(HWND window, UINT message,
                                 WPARAM wParam, LPARAM lParam) {
    switch (message) {
    case WM_LBUTTONDOWN: {
        POINT cursor{};
        GetCursorPos(&cursor);
        gGrabX = cursor.x - gWindowX;
        gGrabY = cursor.y - gWindowY;
        gLastCursorX = cursor.x;
        gLastHorizontalMove = -100.0;
        gDragging = true;
        SetCapture(window);
        return 0;
    }
    case WM_LBUTTONUP:
        if (GetCapture() == window) ReleaseCapture();
        gDragging = false;
        gIdleStart = NowSeconds();
        return 0;
    case WM_CAPTURECHANGED:
        if (GetCapture() != window) {
            gDragging = false;
            gIdleStart = NowSeconds();
        }
        return 0;
    case WM_RBUTTONUP: {
        POINT cursor{};
        GetCursorPos(&cursor);
        HMENU menu = CreatePopupMenu();
        AppendMenuW(menu, MF_STRING, kExitCommand, L"退出 Mon3tr");
        SetForegroundWindow(window);
        const int selected = TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON,
                                            cursor.x, cursor.y, 0, window, nullptr);
        DestroyMenu(menu);
        if (selected == kExitCommand) DestroyWindow(window);
        return 0;
    }
    case WM_SETCURSOR:
        SetCursor(LoadCursorW(nullptr, IDC_HAND));
        return TRUE;
    case WM_KEYDOWN:
        if (wParam == VK_ESCAPE) {
            DestroyWindow(window);
            return 0;
        }
        break;
    case WM_DESTROY:
        gRunning = false;
        PostQuitMessage(0);
        return 0;
    default:
        break;
    }
    return DefWindowProcW(window, message, wParam, lParam);
}

} // namespace

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR commandLine, int) {
    // Coordinates stay in physical display pixels, including on high-DPI screens.
    SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    ULONG_PTR gdiplusToken = 0;
    Gdiplus::GdiplusStartupInput gdiplusInput;
    if (Gdiplus::GdiplusStartup(&gdiplusToken, &gdiplusInput, nullptr)
        != Gdiplus::Ok) return 1;

    const auto assets = ExecutableDirectory() / L"assets";
    const bool loaded = LoadSheet(assets / L"walk-right.png", 8, 8,
                                  gWalkRight)
                        && LoadSheet(assets / L"idle.png", 6, 1, gIdle);
    if (!loaded) {
        MessageBoxW(nullptr, L"找不到完整的动画素材。请将 assets 文件夹与 Mon3tr.exe 放在同一目录。",
                    L"Mon3tr", MB_OK | MB_ICONERROR);
        Gdiplus::GdiplusShutdown(gdiplusToken);
        return 2;
    }
    MirrorWalk();
    if (std::wstring(commandLine).find(L"--self-test") != std::wstring::npos) {
        const bool valid = gWalkRight.size() == kWalkFrames &&
                           gWalkLeft.size() == kWalkFrames &&
                           gIdle.size() == kIdleFrames &&
                           !gWalkRight.front().bgra.empty();
        Gdiplus::GdiplusShutdown(gdiplusToken);
        return valid ? 0 : 3;
    }

    HANDLE singleInstance = CreateMutexW(nullptr, TRUE,
                                          L"Local\\Mon3trStandalonePet");
    if (!singleInstance || GetLastError() == ERROR_ALREADY_EXISTS) {
        if (singleInstance) CloseHandle(singleInstance);
        Gdiplus::GdiplusShutdown(gdiplusToken);
        return 0;
    }

    QueryPerformanceFrequency(&gFrequency);
    QueryPerformanceCounter(&gOrigin);
    WNDCLASSEXW klass{};
    klass.cbSize = sizeof(klass);
    klass.hInstance = instance;
    klass.lpfnWndProc = WindowProcedure;
    klass.lpszClassName = L"Mon3trStandalonePet";
    klass.hCursor = LoadCursorW(nullptr, IDC_HAND);
    klass.hIcon = LoadIconW(instance, MAKEINTRESOURCEW(101));
    klass.hIconSm = klass.hIcon;
    if (!RegisterClassExW(&klass)) return 4;

    RECT area{};
    SystemParametersInfoW(SPI_GETWORKAREA, 0, &area, 0);
    gWindowX = area.right - kWidth - 40;
    gWindowY = area.bottom - kHeight - 24;
    gWindow = CreateWindowExW(WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
                              klass.lpszClassName, L"Mon3tr", WS_POPUP,
                              gWindowX, gWindowY, kWidth, kHeight,
                              nullptr, nullptr, instance, nullptr);
    if (!gWindow || !CreateLayerBuffer()) {
        MessageBoxW(nullptr, L"无法创建透明桌宠窗口。", L"Mon3tr",
                    MB_OK | MB_ICONERROR);
        return 5;
    }
    ShowWindow(gWindow, SW_SHOWNOACTIVATE);
    gIdleStart = NowSeconds();
    if (!Present(gIdle[0])) {
        MessageBoxW(nullptr, L"无法显示桌宠画面。", L"Mon3tr",
                    MB_OK | MB_ICONERROR);
        DestroyWindow(gWindow);
        DestroyLayerBuffer();
        Gdiplus::GdiplusShutdown(gdiplusToken);
        return 6;
    }

    double frameInterval = FrameInterval();
    double nextRefreshCheck = NowSeconds() + 1.0;
    double nextFrame = NowSeconds() + frameInterval;
    timeBeginPeriod(1);
    while (gRunning) {
        MSG message{};
        while (PeekMessageW(&message, nullptr, 0, 0, PM_REMOVE)) {
            if (message.message == WM_QUIT) gRunning = false;
            TranslateMessage(&message);
            DispatchMessageW(&message);
        }
        if (!gRunning) break;
        const double now = NowSeconds();
        if (now >= nextRefreshCheck) {
            frameInterval = FrameInterval();
            nextRefreshCheck = now + 1.0;
        }
        if (now >= nextFrame) {
            Tick(now);
            nextFrame = std::max(nextFrame + frameInterval,
                                 now + frameInterval * 0.25);
        } else {
            const DWORD waitMs = static_cast<DWORD>(
                std::clamp((nextFrame - now) * 1000.0, 0.0, 16.0));
            MsgWaitForMultipleObjectsEx(0, nullptr, waitMs, QS_ALLINPUT,
                                        MWMO_INPUTAVAILABLE);
        }
    }
    timeEndPeriod(1);
    DestroyLayerBuffer();
    ReleaseMutex(singleInstance);
    CloseHandle(singleInstance);
    Gdiplus::GdiplusShutdown(gdiplusToken);
    return 0;
}
