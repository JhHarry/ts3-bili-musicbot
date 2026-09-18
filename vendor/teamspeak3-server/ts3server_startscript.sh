#!/bin/sh
# Copyright (c) 2019 TeamSpeak Systems GmbH
# All rights reserved

BINARYNAME=ts3server
COMMANDLINE_PARAMETERS="" #add any command line parameters you want to pass here
PID_FILE=ts3server.pid

do_start() {
	if [ -e $PID_FILE ]; then
		PID=$(cat "$PID_FILE")
		if (ps -p "$PID" >/dev/null 2>&1); then
			echo "The server is already running, try restart or stop"
			return 1
		else
			echo "$PID_FILE found, but no server running. Possibly your previously started server crashed"
			echo "Please view the logfile for details."
			rm $PID_FILE
		fi
	fi
	if [ $(id -u) -eq 0 ]; then
		echo "WARNING ! For security reasons we advise: DO NOT RUN THE SERVER AS ROOT"
		c=1
		while [ "$c" -le 10 ]; do
			echo -n "!"
			sleep 1
			c=$(($c + 1))
		done
		echo "!"
	fi
	echo "Starting the TeamSpeak 3 server"
	if [ ! -e "$BINARYNAME" ]; then
		echo "Could not find binary, aborting"
		return 5
	fi
	if [ ! -x "$BINARYNAME" ]; then
		echo "${BINARYNAME} is not executable, trying to set it"
		chmod u+x "${BINARYNAME}"
	fi
	if [ ! -x "$BINARYNAME" ]; then
		echo "${BINARNAME} is not exectuable, cannot start TeamSpeak 3 server"
		return 3
	fi
	"./${BINARYNAME}" "${@}" "daemon=1" "pid_file=$PID_FILE"
	if [ $? -eq 0 ]; then
		echo "TeamSpeak 3 server started, for details please view the log file"
	else
		echo "TeamSpeak 3 server could not start"
		return 4
	fi
}

do_stop() {
	if [ ! -e $PID_FILE ]; then
		echo "No server running ($PID_FILE is missing)"
		return 0
	fi
	PID=$(cat "$PID_FILE")
	if (! ps -p "$PID" >/dev/null 2>&1); then
		echo "No server running"
		return 0
	fi

	echo -n "Stopping the TeamSpeak 3 server "
	kill -TERM "$PID" || exit $?
	rm -f $PID_FILE
	c=300
	while [ "$c" -gt 0 ]; do
		if (kill -0 "$PID" 2>/dev/null); then
			echo -n "."
			sleep 1
		else
			break
		fi
		c=$(($c - 1))
	done
	echo
	if [ $c -eq 0 ]; then
		echo "Server is not shutting down cleanly - killing"
		kill -KILL "$PID"
		return $?
	else
		echo "done"
	fi
	return 0
}

do_status() {
	if [ ! -e $PID_FILE ]; then
		echo "No server running ($PID_FILE is missing)"
		return 1
	fi
	PID=$(cat "$PID_FILE")
	if (! ps -p "$PID" >/dev/null 2>&1); then
		echo "Server seems to have died"
		return 1
	fi
	echo "Server is running"
	return 0
}

# change directory to the scripts location
cd $(dirname $([ -x "$(command -v realpath)" ] && realpath "$0" || readlink -f "$0"))

case "$1" in
start)
	shift
	do_start "$@" "$COMMANDLINE_PARAMETERS"
	exit $?
	;;
stop)
	do_stop
	exit $?
	;;
restart)
	shift
	do_stop && (do_start "$@" "$COMMANDLINE_PARAMETERS")
	exit $?
	;;
status)
	do_status
	exit $?
	;;
*)
	echo "Usage: ${0} {start|stop|restart|status}"
	exit 2
	;;
esac
