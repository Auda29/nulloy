cmake_minimum_required(VERSION 3.24)
project(Keyboard218 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
enable_testing()
set(NULLOY_QT_MAJOR "6" CACHE STRING "Qt major version")
find_package(Qt${NULLOY_QT_MAJOR} REQUIRED COMPONENTS Widgets Test)
if(NULLOY_QT_MAJOR STREQUAL "6")
    find_package(Qt6 REQUIRED COMPONENTS Core5Compat)
endif()
find_package(PkgConfig REQUIRED)
pkg_check_modules(GSTREAMER REQUIRED IMPORTED_TARGET gstreamer-1.0 gstreamer-pbutils-1.0)
pkg_check_modules(TAGLIB REQUIRED IMPORTED_TARGET taglib)
get_filename_component(ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)
set(QXT "${ROOT}/3rdParty/qxt-696423b-patched")
add_executable(testKeyboard218 testKeyboard218.cpp nativeShortcutSeam.cpp
    ${ROOT}/src/action.cpp ${QXT}/qxtglobalshortcut.cpp ${QXT}/qxtglobalshortcut.h
    ${ROOT}/src/global.h ${ROOT}/src/common.cpp ${ROOT}/src/settings.cpp
    ${ROOT}/src/utils.cpp ${ROOT}/src/playlistDataItem.cpp ${ROOT}/src/playlistStorage.cpp
    ${ROOT}/src/trackInfoReader.cpp ${ROOT}/src/widgetCollection/playlistWidget.cpp
    ${ROOT}/src/widgetCollection/playlistWidgetItem.cpp
    ${ROOT}/src/plugins/pluginGstreamer/playbackEngineGstreamer.cpp
    ${ROOT}/src/plugins/pluginTaglib/tagReaderTaglib.cpp)
target_include_directories(testKeyboard218 PRIVATE ${ROOT}/src ${ROOT}/src/interfaces
    ${ROOT}/src/plugins ${ROOT}/src/widgetCollection ${QXT}
    ${ROOT}/src/plugins/pluginGstreamer ${ROOT}/src/plugins/pluginTaglib)
target_compile_definitions(testKeyboard218 PRIVATE _TESTS_ QXT_STATIC _N_VERSION_="test-218")
target_link_libraries(testKeyboard218 PRIVATE Qt${NULLOY_QT_MAJOR}::Widgets
    Qt${NULLOY_QT_MAJOR}::Test PkgConfig::GSTREAMER PkgConfig::TAGLIB)
if(NULLOY_QT_MAJOR STREQUAL "6")
    target_link_libraries(testKeyboard218 PRIVATE Qt6::Core5Compat)
endif()
add_test(NAME keyboard218 COMMAND testKeyboard218)
set_tests_properties(keyboard218 PROPERTIES TIMEOUT 120 ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
