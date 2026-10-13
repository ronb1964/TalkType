#!/bin/bash
# Shared by build-deb.sh, build-rpm.sh and package-extension.sh, which each add
# their own files to the release's SHA256SUMS.txt after build-release.sh wrote
# it. The in-app updater verifies the AppImage and the packages against it.

# replace_checksums DIR FILE...
# Drops any old lines for FILE... from DIR/SHA256SUMS.txt, then appends fresh
# sums for them. The file is replaced only when it was read completely, so a
# read error leaves it as it was instead of losing the other checksums.
replace_checksums() {
    local dir="$1"
    shift
    local sums="$dir/SHA256SUMS.txt"
    if [ -f "$sums" ]; then
        if ! awk -v names="$*" '
                BEGIN { n = split(names, list, " "); for (i = 1; i <= n; i++) drop[list[i]] = 1 }
                !($2 in drop)' "$sums" > "$sums.tmp"; then
            rm -f "$sums.tmp"
            echo "❌ Error: could not read $sums. Leaving it untouched." >&2
            return 1
        fi
        mv "$sums.tmp" "$sums"
    fi
    ( cd "$dir" && sha256sum "$@" >> SHA256SUMS.txt )
}
