#!/bin/bash
# macOS: double-click in Finder to open the monitor.
exec "$(cd "$(dirname "$0")" && pwd)/open-monitor.sh"
