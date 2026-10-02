// SPDX-License-Identifier: GPL-3.0-only
#include "singleInstanceStartup.h"

SingleInstanceStartupResult singleInstanceStartup(QtSingleApplication &instance,
                                                  const QString &message,
                                                  int timeout)
{
    if (!instance.isRunning())
        return SingleInstanceStartupResult::Primary;

    return instance.sendMessage(message, timeout)
               ? SingleInstanceStartupResult::MessageDelivered
               : SingleInstanceStartupResult::MessageDeliveryFailed;
}
