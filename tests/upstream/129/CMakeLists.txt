cmake_minimum_required(VERSION 3.24)
project(PlaylistRemoval129 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
enable_testing()
set(NULLOY_QT_MAJOR "6" CACHE STRING "Qt major version (5 or 6)")
find_package(Qt${NULLOY_QT_MAJOR} REQUIRED COMPONENTS Widgets Test)
if(NULLOY_QT_MAJOR STREQUAL "6")
    find_package(Qt6 REQUIRED COMPONENTS Core5Compat)
endif()
find_package(PkgConfig REQUIRED)
pkg_check_modules(GSTREAMER REQUIRED IMPORTED_TARGET gstreamer-1.0 gstreamer-pbutils-1.0)
pkg_check_modules(TAGLIB REQUIRED IMPORTED_TARGET taglib)
get_filename_component(ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)
add_executable(testRemoval129
    testRemoval129.cpp
    ${ROOT}/src/global.h
    ${ROOT}/src/common.cpp
    ${ROOT}/src/settings.cpp
    ${ROOT}/src/utils.cpp
    ${ROOT}/src/playlistDataItem.cpp
    ${ROOT}/src/playlistStorage.cpp
    ${ROOT}/src/trackInfoReader.cpp
    ${ROOT}/src/widgetCollection/playlistWidget.cpp
    ${ROOT}/src/widgetCollection/playlistWidgetItem.cpp
    ${ROOT}/src/plugins/pluginGstreamer/playbackEngineGstreamer.cpp
    ${ROOT}/src/plugins/pluginTaglib/tagReaderTaglib.cpp)
target_include_directories(testRemoval129 PRIVATE
    ${ROOT}/src ${ROOT}/src/interfaces ${ROOT}/src/plugins
    ${ROOT}/src/widgetCollection ${ROOT}/src/plugins/pluginGstreamer
    ${ROOT}/src/plugins/pluginTaglib)
# The existing backend test switch replaces audio/video sinks, not decoding,
# media switching, timers, or state transitions. No application build changes.
target_compile_definitions(testRemoval129 PRIVATE _TESTS_ _N_VERSION_="test-129")
target_link_libraries(testRemoval129 PRIVATE Qt${NULLOY_QT_MAJOR}::Widgets
    Qt${NULLOY_QT_MAJOR}::Test PkgConfig::GSTREAMER PkgConfig::TAGLIB)
if(NULLOY_QT_MAJOR STREQUAL "6")
    target_link_libraries(testRemoval129 PRIVATE Qt6::Core5Compat)
endif()
add_test(NAME removal129 COMMAND testRemoval129 pausedCurrentRemoval removalStates
    nextRemovalHandoff emptyAndDuplicatePaths)
set_tests_properties(removal129 PROPERTIES TIMEOUT 120 ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
foreach(size IN ITEMS 100 1000 5000)
    foreach(pattern IN ITEMS all alternating by-path)
        add_test(NAME removal129-${size}-${pattern}
            COMMAND testRemoval129 largePlaylist:${size}-${pattern})
        set_tests_properties(removal129-${size}-${pattern} PROPERTIES
            TIMEOUT 120 ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
    endforeach()
endforeach()
