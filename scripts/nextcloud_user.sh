#!/bin/bash
#################################################################
# A person's space in Nextcloud: their BeeGFS home and their lab folder.
#
# It is used in two ways:
#   * automatically when an account is created (the tool's `after_create` hook):
#       nextcloud_user.sh {username} {group} {home}
#   * by hand, for somebody who already exists and asked for it:
#       nextcloud_user.sh iprado lab-06 /mnt/beegfs/home/iprado
#
# Why the ACLs are needed: Nextcloud mounts are of type `Local`, which means the
# `apache` user (the web server one) reads them, not the person. The home is 750 and
# owned by its user; the lab folder is 2770 and group-owned. Without an ACL, apache
# sees nothing. The default ACL (`-d`) makes whatever the person creates later work
# for apache too.
#
# It is idempotent: if the mount already exists, it is not duplicated.
#
# And it is **loud when it fails**, on purpose: on 2026-10-14 this script created the
# ACL and then could not mount anything —because Nextcloud did not know the freshly
# created account yet— and it ended with `exit 0`. The hook came out "ok" and nobody
# found out.
#
# WARNING: it has to run where Nextcloud lives (`nodo-nextcloud`). If the tool moves to
# another host, this script needs to `ssh` to the Nextcloud server.
#################################################################
set -u

OCC_DIR="/var/www/html/nextcloud"
OCC="sudo -u apache /usr/bin/php $OCC_DIR/occ"
BASES_HOME="/mnt/beegfs/home"
BASES_LABS="/mnt/beegfs/labs"

username="${1:-}"
group="${2:-}"
home="${3:-}"

if [ ! -f "$OCC_DIR/occ" ]; then
    echo "[nextcloud] there is no Nextcloud on this host: this script has to run on nodo-nextcloud" >&2
    exit 1
fi
if [ -z "$username" ]; then
    echo "[nextcloud] the username is missing" >&2
    exit 1
fi
[ -n "$home" ] || home="$BASES_HOME/$username"
if [ ! -d "$home" ]; then
    echo "[nextcloud] $home does not exist: nothing to mount" >&2
    exit 1
fi

# --- 1. Nextcloud has to know the account ----------------------------------
# The LDAP backend creates it when it lists users; right after a creation it can take
# a few seconds. Without the account, `files_external:create --user` fails.
found=0
for attempt in 1 2 3 4 5 6; do
    if $OCC user:list 2>/dev/null | grep -q -- "- $username:"; then
        found=1
        break
    fi
    sleep 5
done

if [ "$found" -eq 0 ]; then
    echo "[nextcloud] Nextcloud does not see the account '$username' yet: run this script again in a minute" >&2
    exit 1
fi

# --- 2. apache has to be able to read and write the home -------------------
setfacl -m u:apache:rwx "$home" || {
    echo "[nextcloud] could not give apache an ACL on $home" >&2
    exit 1
}
setfacl -d -m u:apache:rwx "$home"

failures=0

# --- 3. mount one point, without duplicating it ----------------------------
# Returns 0 with the id on stdout if it created it, 0 with nothing if it was already
# there, and 1 if it failed.
mount_point() {
    local point="$1" path="$2" id=""
    if $OCC files_external:list "$username" 2>/dev/null | grep -q "| $point "; then
        echo "[nextcloud] $point was already mounted for $username" >&2
        return 0
    fi
    id=$($OCC files_external:create "$point" local null::null \
             --config datadir="$path" --user "$username" 2>&1 \
         | sed -n 's/.*id \([0-9][0-9]*\).*/\1/p')
    if [ -z "$id" ]; then
        echo "[nextcloud] could not create the mount $point for $username" >&2
        return 1
    fi
    $OCC files_external:option "$id" enable_sharing true >/dev/null 2>&1
    echo "$id"
}

home_id=$(mount_point "/home" "$home") || failures=$((failures + 1))
if [ -n "$home_id" ]; then
    echo "[nextcloud] $username: home mounted (id $home_id)"
fi

# --- 4. and their lab folder, if it exists ---------------------------------
if [ -n "$group" ] && [ -d "$BASES_LABS/$group" ]; then
    setfacl -m u:apache:r-x "$BASES_LABS/$group" 2>/dev/null
    lab_id=$(mount_point "/labs/$group" "$BASES_LABS/$group") || failures=$((failures + 1))
    if [ -n "$lab_id" ]; then
        echo "[nextcloud] $username: $group mounted (id $lab_id)"
    fi
fi

if [ "$failures" -gt 0 ]; then
    echo "[nextcloud] $failures mount(s) were left undone for $username" >&2
    exit 1
fi

echo "[nextcloud] done for $username"
