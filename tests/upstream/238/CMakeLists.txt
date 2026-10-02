cmake_minimum_required(VERSION 3.16)
project(upstream238 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_AUTOMOC ON)
find_package(QT NAMES Qt6 Qt5 REQUIRED COMPONENTS Core Gui Test)
find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Core Gui Test)
find_package(PkgConfig REQUIRED)
pkg_check_modules(GST REQUIRED IMPORTED_TARGET gstreamer-1.0 gstreamer-app-1.0 gstreamer-pbutils-1.0)
get_filename_component(ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)
add_executable(testGain testGain.cpp
    ${ROOT}/src/plugins/pluginGstreamer/playbackEngineGstreamer.cpp
    ${ROOT}/src/plugins/pluginGstreamer/playbackEngineGstreamer.h
    ${ROOT}/src/global.h)
target_include_directories(testGain PRIVATE ${ROOT}/src ${ROOT}/src/interfaces ${ROOT}/src/plugins/pluginGstreamer)
target_compile_definitions(testGain PRIVATE _TESTS_)
target_link_libraries(testGain PRIVATE Qt${QT_VERSION_MAJOR}::Core Qt${QT_VERSION_MAJOR}::Gui Qt${QT_VERSION_MAJOR}::Test PkgConfig::GST)
enable_testing()
add_test(NAME gain COMMAND testGain)
set_tests_properties(gain PROPERTIES TIMEOUT 90)
