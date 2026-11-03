package main

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"testing"
)

func TestHealthProtocol6(t *testing.T) {
	for _, protocol := range []int{5, 6, 7} {
		cert, anchor := identity(t, "127.0.0.1", false)
		server := tlsServer(t, cert, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			fmt.Fprintf(w, `{"ok":true,"protocol":%d}`, protocol)
		}))
		remote, _ := url.Parse(server.URL)
		transport := trustedTransport(anchor)
		err := health(context.Background(), remote, transport)
		transport.CloseIdleConnections()
		if (err == nil) != (protocol == 6) {
			t.Fatalf("protocol %d, error %v", protocol, err)
		}
	}
}
