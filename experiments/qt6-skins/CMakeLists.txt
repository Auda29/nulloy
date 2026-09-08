cmake_minimum_required(VERSION 3.24)
project(NulloySkinProbe LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_AUTOMOC ON)
find_package(Qt6 6.8 REQUIRED COMPONENTS Widgets Qml Test UiTools Svg)
enable_testing()
set(SKIN_TEST_PLATFORM "offscreen" CACHE STRING "Qt platform plugin used by tests")
set(SKIN_REFERENCE_DIR "" CACHE PATH "Optional copied 0.9.9 Skins directory")
find_package(ZLIB REQUIRED)
add_library(skin_resources STATIC ../../src/qt6/skinResources.cpp ../../src/qt6/skinResources.h
    ../../3rdParty/qtiocompressor-2.3.1/src/qtiocompressor.cpp
    ../../3rdParty/qtiocompressor-2.3.1/src/qtiocompressor.h)
target_include_directories(skin_resources PUBLIC . ../../3rdParty/qtiocompressor-2.3.1/src)
target_link_libraries(skin_resources PUBLIC Qt6::Widgets ZLIB::ZLIB)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(SKIN_TEST_FONT "C:/Windows/Fonts/arial.ttf" CACHE FILEPATH "Local font used only by the font-loading test")
set(FIXTURE_DIR "${CMAKE_CURRENT_BINARY_DIR}/fixtures")
add_custom_target(skin_fixtures
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/makeFixtures.py
        ${CMAKE_CURRENT_SOURCE_DIR}/../../src/skins ${FIXTURE_DIR} ${SKIN_TEST_FONT}
    VERBATIM)
add_executable(test_skin_resources testSkinResources.cpp)
target_link_libraries(test_skin_resources PRIVATE skin_resources Qt6::Test)
target_compile_definitions(test_skin_resources PRIVATE
    SKIN_SOURCE_ROOT="${CMAKE_CURRENT_SOURCE_DIR}/../../src/skins" FIXTURE_ROOT="${FIXTURE_DIR}")
add_dependencies(test_skin_resources skin_fixtures)
add_test(NAME skin_resources COMMAND test_skin_resources -o ${CMAKE_CURRENT_BINARY_DIR}/resource-results.txt,txt)
set_tests_properties(skin_resources PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=${SKIN_TEST_PLATFORM}")
add_library(skin_bridge STATIC ../../src/qt6/scriptBridge.cpp ../../src/qt6/scriptBridge.h
    ../../src/widgetCollection/label.cpp ../../src/widgetCollection/label.h)
target_link_libraries(skin_bridge PUBLIC Qt6::Widgets Qt6::Qml)
target_include_directories(skin_bridge PUBLIC . ../../src/widgetCollection)
add_executable(test_script_bridge testScriptBridge.cpp)
target_link_libraries(test_script_bridge PRIVATE skin_bridge Qt6::Test)
add_test(NAME script_bridge COMMAND test_script_bridge -o ${CMAKE_CURRENT_BINARY_DIR}/bridge-results.txt,txt)
set_tests_properties(script_bridge PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=${SKIN_TEST_PLATFORM}")

# Explicit opt-in compilation probes of the unmodified bundled dependencies.
# A failing probe records a migration blocker; it must not break the skin tests.
find_package(Qt6 REQUIRED COMPONENTS Network)
set(SINGLE_DIR ../../3rdParty/qtsingleapplication-8fd81b2/src)
add_library(probe_single OBJECT EXCLUDE_FROM_ALL
    ${SINGLE_DIR}/qtsingleapplication.cpp ${SINGLE_DIR}/qtlocalpeer.cpp)
target_include_directories(probe_single PRIVATE ${SINGLE_DIR})
target_link_libraries(probe_single PRIVATE Qt6::Widgets Qt6::Network)
set(QXT_DIR ../../3rdParty/qxt-696423b-patched)
add_library(probe_qxt OBJECT EXCLUDE_FROM_ALL
    ${QXT_DIR}/qxtglobalshortcut.cpp ${QXT_DIR}/qxtglobalshortcut_win.cpp)
target_include_directories(probe_qxt PRIVATE ${QXT_DIR})
target_link_libraries(probe_qxt PRIVATE Qt6::Widgets)
target_compile_definitions(probe_qxt PRIVATE QXT_STATIC)

set(N_SRC ${CMAKE_CURRENT_SOURCE_DIR}/../../src)
add_library(original_widgets STATIC
    fixtureServices.cpp fixtureServices.h
    ${N_SRC}/settings.h ${N_SRC}/global.h
    ${N_SRC}/mainWindow.cpp ${N_SRC}/mainWindow.h
    ${N_SRC}/platform/w7TaskBar.cpp ${N_SRC}/platform/w7TaskBar.h
    ${N_SRC}/widgetCollection/coverWidget.cpp ${N_SRC}/widgetCollection/coverWidget.h
    ${N_SRC}/widgetCollection/coverWidgetPopup.cpp ${N_SRC}/widgetCollection/coverWidgetPopup.h
    ${N_SRC}/widgetCollection/playlistWidget.cpp ${N_SRC}/widgetCollection/playlistWidget.h
    ${N_SRC}/widgetCollection/playlistWidgetItem.cpp ${N_SRC}/widgetCollection/playlistWidgetItem.h
    ${N_SRC}/widgetCollection/slider.cpp ${N_SRC}/widgetCollection/slider.h
    ${N_SRC}/widgetCollection/volumeSlider.cpp ${N_SRC}/widgetCollection/volumeSlider.h
    ${N_SRC}/widgetCollection/waveformSlider.cpp ${N_SRC}/widgetCollection/waveformSlider.h
    ${N_SRC}/playlistDataItem.cpp ${N_SRC}/playlistStorage.cpp ${N_SRC}/waveformPeaks.cpp
    ${N_SRC}/utils.cpp ${N_SRC}/trackInfoReader.cpp ${N_SRC}/trackInfoReader.h)
target_include_directories(original_widgets PUBLIC . ${N_SRC} ${N_SRC}/interfaces ${N_SRC}/platform ${N_SRC}/widgetCollection)
target_link_libraries(original_widgets PUBLIC skin_bridge Qt6::UiTools dwmapi ole32)
add_library(skin_runtime STATIC skinRuntime.cpp skinRuntime.h)
target_link_libraries(skin_runtime PUBLIC original_widgets skin_resources)
add_executable(skin_probe main.cpp)
target_link_libraries(skin_probe PRIVATE skin_runtime)
add_dependencies(skin_probe skin_fixtures)
file(GLOB NATIVE_IMAGES ${N_SRC}/skins/native/*.png)
qt_add_resources(skin_runtime native_images PREFIX "/" BASE ${N_SRC}/skins/native FILES ${NATIVE_IMAGES})
qt_add_resources(skin_runtime app_icon PREFIX "/" BASE ${N_SRC}/icons FILES ${N_SRC}/icons/icon.svg)
add_executable(test_skin_runtime testSkinRuntime.cpp)
target_link_libraries(test_skin_runtime PRIVATE skin_runtime Qt6::Test)
target_compile_definitions(test_skin_runtime PRIVATE
    SKIN_SOURCE_ROOT="${N_SRC}/skins" FIXTURE_ROOT="${FIXTURE_DIR}" REFERENCE_ROOT="${SKIN_REFERENCE_DIR}")
add_dependencies(test_skin_runtime skin_fixtures)
add_test(NAME skin_runtime COMMAND test_skin_runtime -o ${CMAKE_CURRENT_BINARY_DIR}/runtime-results.txt,txt)
set_tests_properties(skin_runtime PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=${SKIN_TEST_PLATFORM}")
add_executable(test_file_drop ${N_SRC}/../tests/testFileDrop.cpp)
target_link_libraries(test_file_drop PRIVATE original_widgets Qt6::Test)
add_dependencies(test_file_drop skin_fixtures)
add_test(NAME file_drop COMMAND test_file_drop -o ${CMAKE_CURRENT_BINARY_DIR}/drop-results.txt,txt)
set_tests_properties(file_drop PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=${SKIN_TEST_PLATFORM}")
