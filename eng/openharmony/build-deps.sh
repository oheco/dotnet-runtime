#!/bin/sh
set -eu
dep_work=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
dep_downloads=${DOTNET_OHOS_DOWNLOADS:-$dep_work/downloads}
dep_root=${DOTNET_OHOS_DEPS_BUILD:-/tmp/oheco-dotnet-deps-verified}
mkdir -p "$dep_root/src" "$dep_root/install" "$dep_root/openssl" "$dep_root/icu-host" "$dep_root/icu-target"
case ${1:-all} in
openssl)
    python3 "$dep_work/verify-inputs.py" openssl
    if [ ! -d "$dep_root/src/openssl-3.5.8" ]; then
        tar -m --no-same-owner -xzf "$dep_downloads/openssl-3.5.8.tar.gz" -C "$dep_root/src"
    fi
    cd "$dep_root/openssl"
    # OpenSSL's no-module build keeps the legacy provider in libcrypto. This
    # preserves .NET DES/RC2 compatibility without a build-directory module path.
    CC="$dep_work/ohos-dep-clang" AR=llvm-ar RANLIB=llvm-ranlib \
    CFLAGS='-O2 -fPIC -D__MUSL__' \
    perl "$dep_root/src/openssl-3.5.8/Configure" linux-aarch64 shared no-module no-tests \
        --prefix="$dep_root/install" --openssldir=/etc/ssl --libdir=lib
    make -j2 build_sw
    make install_sw
    ;;
icu)
    python3 "$dep_work/verify-inputs.py" icu
    if [ ! -d "$dep_root/src/icu" ]; then
        tar -m --no-same-owner -xzf "$dep_downloads/icu4c-78.3-sources.tgz" -C "$dep_root/src"
    fi
    cd "$dep_root/icu-host"
    if [ ! -f Makefile ]; then
        "$dep_root/src/icu/source/configure" --disable-samples --disable-tests --disable-extras \
            --prefix="$dep_root/icu-host-install"
    fi
    make -j2
    cd "$dep_root/icu-target"
    if [ ! -f Makefile ]; then
        CC="$dep_work/ohos-dep-clang" CXX="$dep_work/ohos-dep-clang++" \
        AR=llvm-ar RANLIB=llvm-ranlib CFLAGS='-O2 -fPIC' CXXFLAGS='-O2 -fPIC' \
        "$dep_root/src/icu/source/configure" --host=aarch64-unknown-linux-ohos \
            --with-cross-build="$dep_root/icu-host" --prefix="$dep_root/install" \
            --disable-samples --disable-tests --disable-extras --enable-shared --enable-static
    fi
    # ICU's default data-only link uses -nostdlib, which also removes the OHOS
    # CRT objects and their platform ELF note. Keep the CRT, omit default libs.
    make -C data -f pkgdataMakefile LDFLAGSICUDT=-nodefaultlibs
    rm -f lib/libicudata.so.78.3
    make -j2
    make install
    ;;
*) echo 'Usage: build-deps.sh openssl|icu' >&2; exit 2 ;;
esac
