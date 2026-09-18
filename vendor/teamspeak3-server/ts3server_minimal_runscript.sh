#!/bin/sh

cd $(dirname $([ -x "$(command -v realpath)" ] && realpath "$0" || readlink -f "$0"))
exec ./ts3server $@
