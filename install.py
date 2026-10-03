#!/usr/bin/env python3
"""
Antigravity Conversation Manager — Universal Cross-Platform Installer
Installs the Conversation Manager plugin and registers the MCP Server into Antigravity IDE.
Works on Windows, macOS, and Linux without external dependencies.
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path

def main():
    print("===================================================")
    print(" Installing Antigravity Conversation Manager Plugin")
    print("===================================================")

    script_dir = Path(__file__).resolve().parent
    user_home = Path.home()
    config_dir = user_home / ".gemini" / "config"
    plugins_dir = config_dir / "plugins"
    target_plugin_dir = plugins_dir / "conversation-manager"
    mcp_config_file = config_dir / "mcp_config.json"
    python_exe = sys.executable

    print(f"OS: {sys.platform}")
    print(f"Source Directory: {script_dir}")
    print(f"Config Directory: {config_dir}")
    print(f"Python Executable: {python_exe}")

    # 1. Ensure directories exist
    plugins_dir.mkdir(parents=True, exist_ok=True)

    # 2. Link plugin to ~/.gemini/config/plugins/conversation-manager
    if target_plugin_dir.exists() or target_plugin_dir.is_symlink():
        print(f"Updating existing plugin link at: {target_plugin_dir}")
        try:
            if target_plugin_dir.is_symlink():
                target_plugin_dir.unlink()
            elif sys.platform == "win32":
                subprocess.run(f'cmd /c "rmdir \\"{target_plugin_dir}\\""', shell=True, capture_output=True)
                if target_plugin_dir.exists():
                    target_plugin_dir.rmdir()
            else:
                shutil.rmtree(target_plugin_dir)
        except Exception as e:
            try:
                shutil.rmtree(target_plugin_dir, ignore_errors=True)
            except Exception:
                pass

    try:
        if sys.platform == "win32":
            res = subprocess.run(f'cmd /c "mklink /J \\"{target_plugin_dir}\\" \\"{script_dir}\\""', shell=True, capture_output=True, text=True)
            if res.returncode != 0 and not target_plugin_dir.exists():
                shutil.copytree(script_dir, target_plugin_dir)
        else:
            os.symlink(script_dir, target_plugin_dir)
        print(f"Successfully linked plugin to: {target_plugin_dir}")
    except Exception as e:
        print(f"Notice: Could not symlink ({e}), copying directory...")
        if not target_plugin_dir.exists():
            shutil.copytree(script_dir, target_plugin_dir)

    # 3. Register MCP Server in ~/.gemini/config/mcp_config.json
    mcp_data = {"mcpServers": {}}
    if mcp_config_file.exists():
        try:
            with open(mcp_config_file, "r", encoding="utf-8-sig") as f:
                content = f.read().strip()
                if content:
                    mcp_data = json.loads(content)
                    if "mcpServers" not in mcp_data or not isinstance(mcp_data["mcpServers"], dict):
                        mcp_data["mcpServers"] = {}
        except Exception as e:
            print(f"Notice: Backing up invalid mcp_config.json ({e})")
            shutil.copy2(mcp_config_file, config_dir / "mcp_config.json.bak")
            mcp_data = {"mcpServers": {}}

    mcp_server_script = str((script_dir / "mcp_server.py").resolve())
    mcp_data["mcpServers"]["conversation-manager"] = {
        "command": python_exe,
        "args": [mcp_server_script]
    }

    with open(mcp_config_file, "w", encoding="utf-8") as f:
        json.dump(mcp_data, f, indent=2, ensure_ascii=False)

    print(f"Successfully registered MCP Server in: {mcp_config_file}")

    print("\n---------------------------------------------------")
    print(" Installation Complete!")
    print("---------------------------------------------------")
    print("1. Antigravity agents can now use the 'conversation-manager' skill and MCP tools.")
    print("2. Standalone Web Dashboard can be launched anytime via:")
    if sys.platform == "win32":
        print("   .\\launch-web-ui.bat   OR   python server.py")
    else:
        print("   ./launch-web-ui.sh    OR   python3 server.py")
    print("===================================================\n")

if __name__ == "__main__":
    main()
