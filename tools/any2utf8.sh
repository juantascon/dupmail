#!/bin/bash

#
# Converts all files in a directory to utf8
# Requirements: iconv python-chardetect
#

from="$1"
to="$2"

file="$1"
[ ! -d "$from" -a ! -d "$to" ] && echo "usage: $0 <dir> <dest_dir>" && exit 1

find "$from" -type f -printf '%P\n'| while read file; do
    mkdir -p "$to/$(dirname $file)"
    charset=$(chardetect "$from/$file"|awk '{print $2}')
    case "$charset" in
        "utf-8"|"ascii")
            cp "$from/$file" "$to/$file"
            ;;
        *)
            iconv -f $charset -t utf-8 "$from/$file" > "$to/$file"
            [ "$?" -ne "0" ] && echo "error processing $from/$file"
            ;;
    esac
done
