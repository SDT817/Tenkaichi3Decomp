//go:build ignore

// Fake child for the desktop-launcher test; no game or desktop window is opened.
package main

import (
	"encoding/json"
	"net/http"
	"os"
)

func main() {
	local := os.Getenv("BT3_LOBBY_GATEWAY_LOCAL")
	response, err := http.Get(local + "/healthz")
	if err != nil {
		panic(err)
	}
	defer response.Body.Close()
	var health map[string]interface{}
	if err := json.NewDecoder(response.Body).Decode(&health); err != nil {
		panic(err)
	}
	cwd, _ := os.Getwd()
	value := map[string]interface{}{
		"cwd": cwd, "local": local, "remote": os.Getenv("BT3_LOBBY_GATEWAY_REMOTE"),
		"present_mode_env": os.Getenv("BT3_PRESENT_MODE"), "health": health,
	}
	encoded, _ := json.Marshal(value)
	if err := os.WriteFile("desktop-child.json", encoded, 0600); err != nil {
		panic(err)
	}
}
