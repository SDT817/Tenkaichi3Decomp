package main

import (
	"path/filepath"
	"testing"
)

func TestDesktopPaths(t *testing.T) {
	executable := filepath.Join(t.TempDir(), "中文目录 with spaces", "启动游戏.exe")
	config, game := desktopPaths(executable)
	if config != filepath.Join(filepath.Dir(executable), "bt3_gateway.json") || game != filepath.Join(filepath.Dir(executable), "Tenkaichi3Decomp.exe") {
		t.Fatal("desktop launch must use its own directory")
	}
}
