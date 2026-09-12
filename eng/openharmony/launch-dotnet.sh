#!/bin/sh
# Install as bin/dotnet (SDK) or bin/dotnet-runtime (standalone runtime).
set -eu
dotnet_port_entry=$(readlink -f -- "$0") || exit 1
dotnet_port_bin=${dotnet_port_entry%/*}
DOTNET_ROOT=${dotnet_port_bin%/*}
DOTNET_ROOT_ARM64=$DOTNET_ROOT
export DOTNET_ROOT DOTNET_ROOT_ARM64

if [ -n "${DOTNET_OHOS_TMPDIR:-}" ]; then
    TMPDIR=$DOTNET_OHOS_TMPDIR
else
    case ${TMPDIR:-} in
        ''|/tmp|/tmp/|/storage/Users/currentUser|/storage/Users/currentUser/)
            # The host's shared user directory denies Unix sockets. The SDK's
            # compiler service and runtime diagnostics require an app-private path.
            TMPDIR=/data/storage/el2/base/haps/entry/files/dotnet/tmp
            ;;
    esac
fi
export TMPDIR
if ! (umask 077; mkdir -p -- "$TMPDIR"); then
    printf '%s\n' 'Cannot create the .NET temporary directory; set DOTNET_OHOS_TMPDIR to an app-private writable directory.' >&2
    exit 1
fi
exec "$DOTNET_ROOT/dotnet" "$@"
