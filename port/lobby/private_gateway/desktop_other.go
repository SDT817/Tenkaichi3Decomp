//go:build !windows

package main

import (
	"fmt"
	"os"
	"os/exec"
)

func configureDesktopChild(cmd *exec.Cmd, desktop bool) {}

func reportDesktopError(err error) {
	fmt.Fprintln(os.Stderr, "BT3 connection:", err)
}
