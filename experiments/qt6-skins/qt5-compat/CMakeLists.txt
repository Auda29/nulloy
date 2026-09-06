cmake_minimum_required(VERSION 3.24)
project(NulloyQt5Compatibility LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_AUTOMOC ON)
find_package(Qt5 5.15 REQUIRED COMPONENTS Widgets UiTools WinExtras)
set(N_SRC ${CMAKE_CURRENT_SOURCE_DIR}/../../../src)
# Compile the changed production sources with Qt 5; no fixture services involved.
add_library(qt5_changed_sources OBJECT
    ${N_SRC}/global.h ${N_SRC}/mainWindow.cpp ${N_SRC}/mainWindow.h
    ${N_SRC}/platform/w7TaskBar.cpp ${N_SRC}/platform/w7TaskBar.h
    ${N_SRC}/playlistStorage.cpp
    ${N_SRC}/widgetCollection/playlistWidget.cpp ${N_SRC}/widgetCollection/playlistWidget.h
    ${N_SRC}/widgetCollection/volumeSlider.cpp ${N_SRC}/widgetCollection/volumeSlider.h
    ${N_SRC}/widgetCollection/waveformSlider.cpp ${N_SRC}/widgetCollection/waveformSlider.h)
target_include_directories(qt5_changed_sources PRIVATE ${N_SRC} ${N_SRC}/interfaces ${N_SRC}/platform)
target_link_libraries(qt5_changed_sources PRIVATE Qt5::Widgets Qt5::UiTools Qt5::WinExtras)
target_compile_definitions(qt5_changed_sources PRIVATE UNICODE _UNICODE)
