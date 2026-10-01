cmake_minimum_required(VERSION 3.16)
project(upstream255TrashTests LANGUAGES CXX)

# Standalone regression harness; does not broaden supported player targets.
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
find_package(QT NAMES Qt6 Qt5 REQUIRED COMPONENTS Widgets Test)
find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Widgets Test)
enable_testing()
set(NULLOY_SRC "${CMAKE_CURRENT_LIST_DIR}/../../../src" CACHE PATH "Production source directory")
add_executable(testTrash
    testTrash.cpp
    ${NULLOY_SRC}/platform/trash.cpp
    ${NULLOY_SRC}/settings.cpp
    ${NULLOY_SRC}/settings.h)
target_include_directories(testTrash PRIVATE ${NULLOY_SRC})
target_link_libraries(testTrash PRIVATE Qt${QT_VERSION_MAJOR}::Widgets Qt${QT_VERSION_MAJOR}::Test)
add_test(NAME trashContract COMMAND testTrash)
set_tests_properties(trashContract PROPERTIES
    ENVIRONMENT "QT_QPA_PLATFORM=offscreen"
    TIMEOUT 30)

# Optional engine regression: the shared trash contract remains independently
# buildable without GStreamer. The native CI toolchain supplies these libraries.
find_package(PkgConfig QUIET)
if(PkgConfig_FOUND)
    pkg_check_modules(GST QUIET IMPORTED_TARGET gstreamer-1.0 gstreamer-pbutils-1.0)
    if(GST_FOUND)
        add_executable(testPlaybackFileAccess testPlaybackFileAccess.cpp
            ${NULLOY_SRC}/plugins/pluginGstreamer/playbackEngineGstreamer.cpp
            ${NULLOY_SRC}/plugins/pluginGstreamer/playbackEngineGstreamer.h
            ${NULLOY_SRC}/global.h)
        target_include_directories(testPlaybackFileAccess PRIVATE ${NULLOY_SRC}
            ${NULLOY_SRC}/interfaces ${NULLOY_SRC}/plugins/pluginGstreamer)
        target_compile_definitions(testPlaybackFileAccess PRIVATE _TESTS_)
        target_link_libraries(testPlaybackFileAccess PRIVATE Qt${QT_VERSION_MAJOR}::Widgets
            Qt${QT_VERSION_MAJOR}::Test PkgConfig::GST)
        add_test(NAME playbackFileAccess COMMAND testPlaybackFileAccess)
        set_tests_properties(playbackFileAccess PROPERTIES TIMEOUT 45)
    endif()
endif()

# Opt in explicitly: this creates disposable files and uses the real recycle
# bin. NULLOY_TRASH_TEST_ROOT and NULLOY_TRASH_EXPECT_RECYCLE select the volume
# and expected behavior without modifying the user's recycle-bin settings.
option(NULLOY_NATIVE_TRASH_TESTS "Test the real Windows recycle bin" OFF)
if(WIN32 AND NULLOY_NATIVE_TRASH_TESTS)
    add_executable(testWindowsTrash testWindowsTrash.cpp
        ${NULLOY_SRC}/platform/trash_win.cpp)
    target_include_directories(testWindowsTrash PRIVATE ${NULLOY_SRC})
    target_link_libraries(testWindowsTrash PRIVATE Qt${QT_VERSION_MAJOR}::Widgets Qt${QT_VERSION_MAJOR}::Test)
    add_test(NAME windowsTrashNative COMMAND testWindowsTrash)
    set_tests_properties(windowsTrashNative PROPERTIES
        ENVIRONMENT "QT_QPA_PLATFORM=offscreen" TIMEOUT 30)
endif()
