#!/bin/bash
echo "--- Starting Apple Dictation Deep Clean ---"

# 1. Kill active speech and dictation processes
echo "Killing background speech processes..."
killall -9 DictationIM 2>/dev/null
killall -9 com.apple.SpeechRecognitionCore.speechrecognitiond 2>/dev/null
killall -9 com.apple.SpeechRecognitionCore.brokerd 2>/dev/null
killall -9 assistantd 2>/dev/null

# 2. Clear corrupted preference files
echo "Removing preference files..."
rm -f ~/Library/Preferences/com.apple.assistant.plist
rm -f ~/Library/Preferences/com.apple.assistant.support.plist
rm -f ~/Library/Preferences/com.apple.SpeechRecognitionCore.plist

# 3. Purge cache folders
echo "Purging speech recognition caches..."
rm -rf ~/Library/Caches/com.apple.SpeechRecognitionCore.speechrecognitiond
rm -rf ~/Library/Caches/com.apple.assistantd

# 4. Reset Core Audio (Requires Password)
echo "Resetting Core Audio (Enter your Mac password if prompted)..."
sudo killall coreaudiod

echo "--- Clean Complete ---"
echo "ACTION REQUIRED: Go to System Settings > Keyboard. Toggle Dictation OFF, then back ON."
