// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

#pragma once

#include <dlfcn.h>

#ifdef TARGET_OPENHARMONY
#include <limits.h>
#include <stdio.h>
#include <string.h>

// The OpenHarmony loader does not use a dlopen caller's RUNPATH to find a
// library by name. Resolve bundled ICU/OpenSSL beside the calling module.
// For statically linked NativeAOT shims, dladdr identifies the executable.
static inline void* LoadLibraryRelativeToModule(const char* name, int flags)
{
    Dl_info module;
    if (strchr(name, '/') == NULL &&
        dladdr((void*)&LoadLibraryRelativeToModule, &module) != 0 && module.dli_fname != NULL)
    {
        const char* separator = strrchr(module.dli_fname, '/');
        if (separator != NULL)
        {
            size_t directoryLength = (size_t)(separator - module.dli_fname) + 1;
            size_t nameLength = strlen(name);
            char path[PATH_MAX];
            if (directoryLength < sizeof(path) && nameLength < sizeof(path) - directoryLength)
            {
                memcpy(path, module.dli_fname, directoryLength);
                memcpy(path + directoryLength, name, nameLength + 1);
                void* library = dlopen(path, flags);
                if (library != NULL)
                    return library;
            }
        }
    }
    return dlopen(name, flags);
}
#else
#define LoadLibraryRelativeToModule(name, flags) dlopen(name, flags)
#endif
