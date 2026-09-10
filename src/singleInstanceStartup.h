// SPDX-License-Identifier: GPL-3.0-only
#ifndef NULLOY_SINGLE_INSTANCE_STARTUP_H
#define NULLOY_SINGLE_INSTANCE_STARTUP_H

#include <qtsingleapplication.h>

enum class SingleInstanceStartupResult {
    Primary,
    MessageDelivered,
    MessageDeliveryFailed,
};

SingleInstanceStartupResult singleInstanceStartup(QtSingleApplication &instance,
                                                  const QString &message,
                                                  int timeout = 5000);

#endif // NULLOY_SINGLE_INSTANCE_STARTUP_H
