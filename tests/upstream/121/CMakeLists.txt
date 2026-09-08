cmake_minimum_required(VERSION 3.24)
project(Shuffle121 LANGUAGES CXX)
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
add_executable(testShuffle121 testShuffle121.cpp
    ${ROOT}/src/global.h ${ROOT}/src/common.cpp ${ROOT}/src/settings.cpp
    ${ROOT}/src/utils.cpp ${ROOT}/src/playlistDataItem.cpp ${ROOT}/src/playlistStorage.cpp
    ${ROOT}/src/trackInfoReader.cpp ${ROOT}/src/widgetCollection/playlistWidget.cpp
    ${ROOT}/src/widgetCollection/playlistWidgetItem.cpp
    ${ROOT}/src/plugins/pluginGstreamer/playbackEngineGstreamer.cpp
    ${ROOT}/src/plugins/pluginTaglib/tagReaderTaglib.cpp)
target_include_directories(testShuffle121 PRIVATE ${ROOT}/src ${ROOT}/src/interfaces
    ${ROOT}/src/plugins ${ROOT}/src/widgetCollection
    ${ROOT}/src/plugins/pluginGstreamer ${ROOT}/src/plugins/pluginTaglib)
target_compile_definitions(testShuffle121 PRIVATE _TESTS_ _N_VERSION_="test-121")
target_link_libraries(testShuffle121 PRIVATE Qt${NULLOY_QT_MAJOR}::Widgets
    Qt${NULLOY_QT_MAJOR}::Test PkgConfig::GSTREAMER PkgConfig::TAGLIB)
if(NULLOY_QT_MAJOR STREQUAL "6")
    target_link_libraries(testShuffle121 PRIVATE Qt6::Core5Compat)
endif()
foreach(size IN ITEMS 0 1 100 5000)
    foreach(state IN ITEMS 0 1 2)
        add_test(NAME shuffle121-${size}-${state}
            COMMAND testShuffle121 preservesPlaylist:${size}-${state})
        set_tests_properties(shuffle121-${size}-${state} PROPERTIES
            TIMEOUT 120 ENVIRONMENT "QT_QPA_PLATFORM=offscreen")
    endforeach()
endforeach()
