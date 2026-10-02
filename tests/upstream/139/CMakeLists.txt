cmake_minimum_required(VERSION 3.16)
project(Waveform139 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOGEN_PARALLEL 1)
set(NULLOY_QT_MAJOR 6 CACHE STRING "Qt major version (5 or 6)")
find_package(Qt${NULLOY_QT_MAJOR} REQUIRED COMPONENTS Core Gui Test)
find_package(PkgConfig REQUIRED)
pkg_check_modules(GSTREAMER REQUIRED IMPORTED_TARGET gstreamer-1.0)
get_filename_component(ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)
add_executable(testWaveform139 testWaveform139.cpp
    ${ROOT}/src/plugins/pluginGstreamer/waveformBuilderGstreamer.cpp
    ${ROOT}/src/plugins/pluginGstreamer/waveformBuilderGstreamer.h
    ${ROOT}/src/plugins/abstractWaveformBuilder.cpp
    ${ROOT}/src/waveformPeaks.cpp ${ROOT}/src/common.cpp)
target_include_directories(testWaveform139 PRIVATE ${ROOT}/src ${ROOT}/src/interfaces
    ${ROOT}/src/plugins ${ROOT}/src/plugins/pluginGstreamer)
find_program(FFMPEG_EXECUTABLE ffmpeg REQUIRED)
target_compile_definitions(testWaveform139 PRIVATE _N_PORTABLE_FORK_
    "FFMPEG_EXECUTABLE=\"${FFMPEG_EXECUTABLE}\"")
target_link_libraries(testWaveform139 PRIVATE Qt${NULLOY_QT_MAJOR}::Core
    Qt${NULLOY_QT_MAJOR}::Gui Qt${NULLOY_QT_MAJOR}::Test PkgConfig::GSTREAMER)
enable_testing()
add_test(NAME waveform139 COMMAND testWaveform139)
set_tests_properties(waveform139 PROPERTIES TIMEOUT 180 RUN_SERIAL TRUE)
