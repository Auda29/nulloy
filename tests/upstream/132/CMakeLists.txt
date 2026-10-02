# Snapshot adapted from the inspected #211 native harness; no cross-worktree dependency.
# Platform shims disable desktop hotkeys and the Windows-only font query on Linux.
cmake_minimum_required(VERSION 3.24)
project(Upstream132 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)
get_filename_component(ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)
set(CMAKE_AUTOUIC_SEARCH_PATHS "${ROOT}/src" "${ROOT}/src/skins/native")
find_package(Qt6 6.8 REQUIRED COMPONENTS Widgets Test Qml Svg SvgWidgets Network UiTools Core5Compat)
find_package(ZLIB REQUIRED)
find_package(PkgConfig REQUIRED)
pkg_check_modules(GST REQUIRED IMPORTED_TARGET gstreamer-1.0 gstreamer-pbutils-1.0)
pkg_check_modules(TAGLIB REQUIRED IMPORTED_TARGET taglib)
enable_testing()
add_library(options132 INTERFACE)
target_include_directories(options132 INTERFACE "${ROOT}/src" "${ROOT}/src/interfaces"
    "${ROOT}/src/platform" "${ROOT}/src/plugins" "${ROOT}/src/widgetCollection")
target_compile_definitions(options132 INTERFACE _N_SHARED_BUILD_ _N_NO_SKINS_ _N_NO_UPDATE_CHECK_
    _N_PORTABLE_FORK_ "_N_VERSION_=\"132-test\"" "N_LIBDIR=\"lib\"")
target_link_libraries(options132 INTERFACE Qt6::Widgets Qt6::Svg Qt6::SvgWidgets Qt6::Core5Compat)
set(QXT "${ROOT}/3rdParty/qxt-696423b-patched")
set(SINGLE "${ROOT}/3rdParty/qtsingleapplication-8fd81b2/src")
set(COMPRESS "${ROOT}/3rdParty/qtiocompressor-2.3.1/src")
add_library(deps132 STATIC "${QXT}/qxtglobalshortcut.cpp" "${QXT}/qxtglobalshortcut.h"
    shortcutPlatform.cpp "${SINGLE}/qtsingleapplication.cpp" "${SINGLE}/qtlocalpeer.cpp"
    "${COMPRESS}/qtiocompressor.cpp")
target_include_directories(deps132 PUBLIC "${QXT}" "${SINGLE}" "${COMPRESS}")
target_compile_definitions(deps132 PUBLIC QXT_STATIC)
target_link_libraries(deps132 PUBLIC options132 Qt6::Network ZLIB::ZLIB)
file(GLOB CORE CONFIGURE_DEPENDS "${ROOT}/src/*.cpp" "${ROOT}/src/*.h"
    "${ROOT}/src/widgetCollection/*.cpp" "${ROOT}/src/widgetCollection/*.h")
foreach(legacy main.cpp scriptEngine.cpp scriptQtPrototypes.cpp scriptQtPrototypes.h
        skinFileSystem.cpp skinFileSystem.h skinLoader.cpp skinLoader.h)
    list(REMOVE_ITEM CORE "${ROOT}/src/${legacy}")
endforeach()
list(REMOVE_ITEM CORE "${ROOT}/src/widgetCollection/widgetCollection.cpp"
    "${ROOT}/src/widgetCollection/widgetCollection.h")
add_library(core132 OBJECT ${CORE} "${ROOT}/src/qt6/scriptEngine.cpp"
    "${ROOT}/src/qt6/scriptBridge.cpp" "${ROOT}/src/qt6/scriptBridge.h"
    "${ROOT}/src/platform/trash.cpp" "${ROOT}/src/platform/trash_x11.cpp"
    "${ROOT}/src/no-skins.qrc" "${ROOT}/src/icons/icons.qrc")
target_include_directories(core132 PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/platform")
target_link_libraries(core132 PUBLIC options132 deps132 Qt6::Qml Qt6::UiTools)
foreach(plugin IN ITEMS Gstreamer Taglib)
    file(GLOB SOURCES CONFIGURE_DEPENDS "${ROOT}/src/plugins/plugin${plugin}/*.cpp"
        "${ROOT}/src/plugins/plugin${plugin}/*.h")
    list(FILTER SOURCES EXCLUDE REGEX "tagReaderGstreamer\\.(cpp|h)$")
    add_library(plugin${plugin} MODULE ${SOURCES} "${ROOT}/src/global.h" "${ROOT}/src/common.cpp"
        "${ROOT}/src/plugins/abstractWaveformBuilder.cpp" "${ROOT}/src/plugins/abstractWaveformBuilder.h"
        "${ROOT}/src/waveformPeaks.cpp")
    target_compile_definitions(plugin${plugin} PRIVATE _TESTS_)
    target_link_libraries(plugin${plugin} PRIVATE options132 PkgConfig::GST PkgConfig::TAGLIB)
    set_target_properties(plugin${plugin} PROPERTIES LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/plugins")
endforeach()
add_executable(test132 test132.cpp)
target_link_libraries(test132 PRIVATE core132 Qt6::Test)
add_dependencies(test132 pluginGstreamer pluginTaglib)
add_test(NAME upstream132 COMMAND test132)
set_tests_properties(upstream132 PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen" TIMEOUT 120)
