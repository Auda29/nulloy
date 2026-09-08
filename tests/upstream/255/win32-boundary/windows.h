#pragma once

// Compile-only OS boundary for the Linux-hosted regression test. This is NOT
// a Windows SDK or ABI test. Production builds never include this directory.
#include <cstddef>
using BOOL = int;
