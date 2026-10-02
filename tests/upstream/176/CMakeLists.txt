cmake_minimum_required(VERSION 3.16)
project(NulloyIssue176 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_AUTOMOC ON)
find_package(QT NAMES Qt6 Qt5 REQUIRED COMPONENTS Core Gui Test)
find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Core Gui Test)
find_package(PkgConfig REQUIRED)
pkg_check_modules(GST REQUIRED IMPORTED_TARGET gstreamer-1.0 gstreamer-pbutils-1.0)
set(ROOT "${CMAKE_CURRENT_LIST_DIR}/../../..")
add_executable(testIssue176 testIssue176.cpp
    ${ROOT}/src/plugins/pluginGstreamer/playbackEngineGstreamer.cpp ${ROOT}/src/global.h)
target_include_directories(testIssue176 PRIVATE ${ROOT}/src ${ROOT}/src/interfaces
    ${ROOT}/src/plugins/pluginGstreamer)
target_compile_definitions(testIssue176 PRIVATE _TESTS_)
target_link_libraries(testIssue176 PRIVATE Qt${QT_VERSION_MAJOR}::Core
    Qt${QT_VERSION_MAJOR}::Gui Qt${QT_VERSION_MAJOR}::Test PkgConfig::GST)
enable_testing()
add_test(NAME issue176 COMMAND testIssue176)
set_tests_properties(issue176 PROPERTIES TIMEOUT 180)
