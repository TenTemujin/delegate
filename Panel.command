#!/bin/bash
# macOS: double-click in Finder to open the control panel.
exec "$(cd "$(dirname "$0")" && pwd)/open-panel.sh"
