#!/bin/sh
# Read-only target probe, sent over the pinned SSH connection by test-camera.sh.
camera_root_identity() {
    # The caller supplies the target's udev UUID directory. Never accept the
    # boot partition's UUID or guess an identity when links are ambiguous.
    uuid_directory=$1
    root_source=$(findmnt -n -o SOURCE /) || return 1
    parent=$(lsblk -no PKNAME "$root_source") || return 1
    parent=$(printf '%s' "$parent" | tr -d '[:space:]')
    transport=$(lsblk -dn -o TRAN "/dev/$parent") || return 1
    transport=$(printf '%s' "$transport" | tr -d '[:space:]')
    root_uuid=$(lsblk -no UUID "$root_source" 2>/dev/null) || root_uuid=''
    # Whitespace-only output is absent data; never splice parts of a UUID by
    # deleting embedded whitespace from a nonempty value.
    case "$root_uuid" in
        *[![:space:]]*) ;;
        *) root_uuid='' ;;
    esac
    if [ -z "$root_uuid" ]; then
        [ -e "$root_source" ] || return 1
        root_device=$(readlink -f "$root_source") || return 1
        [ -n "$root_device" ] || return 1
        for uuid_link in "$uuid_directory"/*; do
            # -f is supported by the target BusyBox; -e is not a readlink option.
            [ -L "$uuid_link" ] && [ -e "$uuid_link" ] || continue
            candidate_device=$(readlink -f "$uuid_link") || continue
            [ "$candidate_device" = "$root_device" ] || continue
            if [ -n "$root_uuid" ]; then
                printf 'ERROR: camera root filesystem UUID links are ambiguous\n' >&2
                return 1
            fi
            root_uuid=${uuid_link##*/}
        done
    fi
    # This image's root filesystem is ext4. Reject malformed/multiple values
    # instead of merging them into an identity or passing control delimiters.
    case "$root_uuid" in
        *[!0-9a-fA-F-]*)
            printf 'ERROR: camera root filesystem UUID contains invalid characters\n' >&2
            return 1
            ;;
    esac
    if ! printf '%s\n' "$root_uuid" | LC_ALL=C grep -Eq \
        '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'; then
        printf 'ERROR: camera root filesystem UUID is missing or invalid\n' >&2
        return 1
    fi
    printf '%s|%s|%s|%s\n' "$root_source" "/dev/$parent" "$transport" "$root_uuid"
}
