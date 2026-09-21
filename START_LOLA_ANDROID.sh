#!/data/data/com.termux/files/usr/bin/bash
set -e
cd "$(dirname "$0")"

if ! command -v python >/dev/null 2>&1; then
  echo "Python is not installed in Termux."
  echo "Run: pkg update && pkg install python"
  exit 1
fi

echo "Starting Lola Mobile on Android..."
echo "Open http://127.0.0.1:8766 if the browser does not open automatically."
python lola_mobile.py
