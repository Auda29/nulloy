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

# Exercise the real Windows adapter against a controlled shell boundary on
# Linux; this deliberately does not claim native Windows API/ABI coverage.
if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    add_executable(testWindowsTrash testWindowsTrash.cpp
        ${NULLOY_SRC}/platform/trash_win.cpp ${NULLOY_SRC}/platform/trash.cpp
        ${NULLOY_SRC}/settings.cpp ${NULLOY_SRC}/settings.h)
    target_include_directories(testWindowsTrash PRIVATE win32-boundary ${NULLOY_SRC})
    target_link_libraries(testWindowsTrash PRIVATE Qt${QT_VERSION_MAJOR}::Widgets Qt${QT_VERSION_MAJOR}::Test)
    add_test(NAME windowsTrashBoundary COMMAND testWindowsTrash)
    set_tests_properties(windowsTrashBoundary PROPERTIES
        ENVIRONMENT "QT_QPA_PLATFORM=offscreen" TIMEOUT 30)
endif()
