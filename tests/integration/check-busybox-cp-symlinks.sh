#!/bin/sh
# Bounded CVE-2007-4998/normal-copy checks for a configured BusyBox binary.
# Usage: sh check-busybox-cp-symlinks.sh /absolute/busybox [applet|cp]
# "cp" mode tests the installed cp symlink directly. No root or real victim files.
set -eu
umask 077
LC_ALL=C
export LC_ALL
binary=${1:?absolute BusyBox binary or cp entry required}
mode=${2:-applet}
case "$binary" in /*) ;; *) echo 'An absolute executable path is required' >&2; exit 2 ;; esac
case "$mode" in applet|cp) ;; *) exit 2 ;; esac
test -x "$binary"
test "$(id -u)" != 0 || { echo 'Run as an unprivileged user' >&2; exit 2; }
scratch=$(mktemp -d "${TMPDIR:-/tmp}/busybox-cp-check.XXXXXXXX")
cleanup() { rm -rf -- "$scratch"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

run_cp() {
    if test "$mode" = applet; then
        "$binary" cp "$@"
    else
        "$binary" "$@"
    fi
}

victim_unchanged() {
    if test "$exists" = existing; then
        test -f "$c/victim" && test "$(cat "$c/victim")" = ORIGINAL
    else
        test ! -e "$c/victim" && test ! -L "$c/victim"
    fi
}

same_basename() {
    flags=$1; exists=$2; link_kind=$3
    mkdir "$c/a" "$c/b" "$c/dst" || return 1
    if test "$exists" = existing; then printf 'ORIGINAL\n' >"$c/victim"; fi
    printf 'PAYLOAD\n' >"$c/b/item" || return 1
    if test "$link_kind" = relative; then link_value=../victim; else link_value=$c/victim; fi
    ln -s "$link_value" "$c/a/item" || return 1
    # flags is one of this file's fixed option strings, never external input.
    run_cp $flags "$c/a/item" "$c/b/item" "$c/dst" >"$c/stdout" 2>"$c/stderr" || return 1
    victim_unchanged || return 1
    test ! -L "$c/dst/item" && test "$(cat "$c/dst/item")" = PAYLOAD || return 1
    test -L "$c/a/item" && test "$(readlink "$c/a/item")" = "$link_value"
}

recursive_merge() {
    flags=$1; exists=$2
    mkdir -p "$c/a/tree/sub" "$c/b/tree/sub" "$c/dst" || return 1
    if test "$exists" = existing; then printf 'ORIGINAL\n' >"$c/victim"; fi
    ln -s "$c/victim" "$c/a/tree/sub/item" || return 1
    printf 'PAYLOAD\n' >"$c/b/tree/sub/item" || return 1
    run_cp $flags "$c/a/tree" "$c/b/tree" "$c/dst" >"$c/stdout" 2>"$c/stderr" || return 1
    victim_unchanged || return 1
    test ! -L "$c/dst/tree/sub/item" && test "$(cat "$c/dst/tree/sub/item")" = PAYLOAD
}

normal_copy() {
    operation=$1
    printf 'SOURCE\n' >"$c/source" || return 1
    case "$operation" in
        create)
            run_cp "$c/source" "$c/dest" || return 1
            test "$(cat "$c/dest")" = SOURCE ;;
        overwrite)
            printf 'LONG-OLD-CONTENT\n' >"$c/dest" || return 1
            run_cp "$c/source" "$c/dest" || return 1
            test "$(cat "$c/dest")" = SOURCE ;;
        recursive)
            mkdir -p "$c/tree/sub" || return 1
            printf 'NESTED\n' >"$c/tree/sub/item" || return 1
            run_cp -a "$c/tree" "$c/dest" || return 1
            test "$(cat "$c/dest/sub/item")" = NESTED ;;
        preserve-link)
            ln -s source "$c/link" || return 1
            run_cp -P "$c/link" "$c/dest" || return 1
            test -L "$c/dest" && test "$(readlink "$c/dest")" = source ;;
        preserve-dangling-link)
            ln -s absent "$c/link" || return 1
            run_cp -a "$c/link" "$c/dest" || return 1
            test -L "$c/dest" && test "$(readlink "$c/dest")" = absent && test ! -e "$c/absent" ;;
        dereference-source)
            ln -s source "$c/link" || return 1
            run_cp -L "$c/link" "$c/dest" || return 1
            test ! -L "$c/dest" && test "$(cat "$c/dest")" = SOURCE ;;
        no-clobber)
            printf 'OLD\n' >"$c/dest" || return 1
            run_cp -n "$c/source" "$c/dest" || return 1
            test "$(cat "$c/dest")" = OLD ;;
        no-clobber-link)
            printf 'ORIGINAL\n' >"$c/victim" || return 1
            ln -s victim "$c/dest" || return 1
            run_cp -n "$c/source" "$c/dest" || return 1
            test -L "$c/dest" && test "$(cat "$c/victim")" = ORIGINAL ;;
        interactive-no)
            printf 'OLD\n' >"$c/dest" || return 1
            printf 'n\n' | run_cp -i "$c/source" "$c/dest" >"$c/stdout" 2>"$c/stderr" || return 1
            test "$(cat "$c/dest")" = OLD ;;
        interactive-yes)
            printf 'ORIGINAL\n' >"$c/victim" || return 1
            ln -s victim "$c/dest" || return 1
            printf 'y\n' | run_cp -i "$c/source" "$c/dest" >"$c/stdout" 2>"$c/stderr" || return 1
            test ! -L "$c/dest" && test "$(cat "$c/dest")" = SOURCE && test "$(cat "$c/victim")" = ORIGINAL ;;
        remove-destination)
            printf 'ORIGINAL\n' >"$c/victim" || return 1
            ln -s victim "$c/dest" || return 1
            run_cp --remove-destination "$c/source" "$c/dest" || return 1
            test ! -L "$c/dest" && test "$(cat "$c/dest")" = SOURCE && test "$(cat "$c/victim")" = ORIGINAL ;;
        *) return 1 ;;
    esac
}

number=0
failures=0
check() {
    label=$1
    shift
    number=$((number + 1))
    c=$scratch/$number
    mkdir "$c"
    # Every operation in these functions checks its return explicitly: sh's
    # errexit is suppressed for function calls evaluated by an if condition.
    if ( "$@" ); then
        printf 'ok %s - %s\n' "$number" "$label"
    else
        printf 'not ok %s - %s\n' "$number" "$label"
        failures=$((failures + 1))
    fi
}

printf 'TAP version 13\n'
for flags in -a -R -RP -d -P; do
    for exists in existing missing; do
        for link_kind in relative absolute; do
            check "same-basename $flags $exists $link_kind" same_basename "$flags" "$exists" "$link_kind"
        done
    done
done
for flags in -a -R -RP; do
    for exists in existing missing; do
        check "recursive-merge $flags $exists" recursive_merge "$flags" "$exists"
    done
done
for operation in create overwrite recursive preserve-link preserve-dangling-link dereference-source no-clobber no-clobber-link interactive-no interactive-yes remove-destination; do
    check "ordinary $operation" normal_copy "$operation"
done
printf '1..%s\n' "$number"
test "$failures" = 0
