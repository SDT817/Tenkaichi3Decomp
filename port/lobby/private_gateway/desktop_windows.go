package main

import (
	"os/exec"
	"syscall"
	"unsafe"
)

func configureDesktopChild(cmd *exec.Cmd, desktop bool) {
	if desktop {
		cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	}
}

func reportDesktopError(err error) {
	title, _ := syscall.UTF16PtrFromString("电光火石3：启动失败")
	text, _ := syscall.UTF16PtrFromString("无法启动游戏。请确认启动器与游戏文件放在同一目录。\n可查看该目录中的 bt3-launcher.log。\n\n" + err.Error())
	syscall.NewLazyDLL("user32.dll").NewProc("MessageBoxW").Call(0, uintptr(unsafe.Pointer(text)), uintptr(unsafe.Pointer(title)), 0x10)
}
