#!/usr/bin/zsh
# Run on HarmonyOS after all ELF rewriting/stripping and before packaging.
set -eu
if (( $# != 2 )); then
    print -u2 'Usage: sign-tree.zsh <staged-install-root> <log-directory>'
    exit 2
fi
sign_root=${1:A}
sign_logs=${2:A}
sign_tool=$(command -v binary-sign-tool) || exit 2
sign_reader=$(command -v llvm-readelf) || exit 2
mkdir -p -- "$sign_logs"
integer sign_count=0
for sign_file in "$sign_root"/**/*(DN.); do
    sign_magic=''
    IFS= read -rk 4 -u 0 sign_magic < "$sign_file" || continue
    [[ $sign_magic == $'\x7fELF' ]] || continue
    sign_header=$("$sign_reader" -h "$sign_file")
    # NativeAOT .o inputs are relocatable objects, not runnable binaries.
    [[ $sign_header == *'Type:'*'DYN'* || $sign_header == *'Type:'*'EXEC'* ]] || continue
    sign_program_headers=$("$sign_reader" -lW "$sign_file")
    integer sign_loadable=0
    for sign_line in "${(@f)sign_program_headers}"; do
        sign_fields=(${=sign_line})
        (( ${#sign_fields} >= 7 )) || continue
        [[ $sign_fields[1] == LOAD || $sign_fields[1] == DYNAMIC ]] || continue
        (( sign_fields[5] != 0 )) || continue
        sign_flags="${(j: :)sign_fields[7,-1]}"
        if [[ $sign_fields[1] == DYNAMIC || $sign_flags == *E* ]]; then
            sign_loadable=1
            break
        fi
    done
    # Detached ELF debug files retain DYN/EXEC headers but have no code or
    # dynamic table bytes. Preserve their CRC for .gnu_debuglink consumers.
    (( sign_loadable )) || continue
    (( ++sign_count ))
    sign_temp="$sign_file.oheco-sign.$$"
    rm -f -- "$sign_temp"
    print -r -- "${sign_file#$sign_root/}" > "$sign_logs/$sign_count.path"
    if ! "$sign_tool" sign -inFile "$sign_file" -outFile "$sign_temp" -selfSign 1 > "$sign_logs/$sign_count.log" 2>&1; then
        rm -f -- "$sign_temp"
        print -u2 -- "Signing failed: $sign_file; see $sign_logs/$sign_count.log"
        exit 1
    fi
    chmod 755 -- "$sign_temp"
    mv -f -- "$sign_temp" "$sign_file"
done
print -- "Signed $sign_count ELF files."
