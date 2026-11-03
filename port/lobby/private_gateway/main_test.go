package main

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"io"
	"math/big"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func identity(t *testing.T, ip string, expired bool) (tls.Certificate, *x509.Certificate) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	start, end := time.Now().Add(-time.Hour), time.Now().Add(time.Hour)
	if expired {
		start, end = time.Now().Add(-48*time.Hour), time.Now().Add(-24*time.Hour)
	}
	spec := &x509.Certificate{SerialNumber: big.NewInt(1), NotBefore: start, NotAfter: end,
		IPAddresses: []net.IP{net.ParseIP(ip)}, KeyUsage: x509.KeyUsageDigitalSignature,
		ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}
	der, err := x509.CreateCertificate(rand.Reader, spec, spec, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	cert, err := x509.ParseCertificate(der)
	if err != nil {
		t.Fatal(err)
	}
	return tls.Certificate{Certificate: [][]byte{der}, PrivateKey: key}, cert
}

func tlsServer(t *testing.T, cert tls.Certificate, handler http.Handler) *httptest.Server {
	t.Helper()
	server := httptest.NewUnstartedServer(handler)
	server.Config.ErrorLog = nil
	server.TLS = &tls.Config{Certificates: []tls.Certificate{cert}, MinVersion: tls.VersionTLS12}
	server.StartTLS()
	t.Cleanup(server.Close)
	return server
}

func TestTLSIdentity(t *testing.T) {
	good, anchor := identity(t, "127.0.0.1", false)
	wrong, _ := identity(t, "127.0.0.1", false)
	badName, badNameAnchor := identity(t, "192.0.2.1", false)
	expired, expiredAnchor := identity(t, "127.0.0.1", true)
	for _, item := range []struct {
		name   string
		cert   tls.Certificate
		anchor *x509.Certificate
		want   bool
	}{
		{"trusted", good, anchor, true}, {"untrusted", wrong, anchor, false},
		{"wrong_hostname", badName, badNameAnchor, false}, {"expired", expired, expiredAnchor, false},
	} {
		t.Run(item.name, func(t *testing.T) {
			server := tlsServer(t, item.cert, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { io.WriteString(w, `{"ok":true}`) }))
			tr := trustedTransport(item.anchor)
			defer tr.CloseIdleConnections()
			response, err := (&http.Client{Transport: tr}).Get(server.URL)
			if response != nil {
				response.Body.Close()
			}
			if (err == nil) != item.want {
				t.Fatalf("TLS accepted=%v, want=%v, error=%v", err == nil, item.want, err)
			}
		})
	}
}

func TestPrivateUpdatesStream(t *testing.T) {
	cert, anchor := identity(t, "127.0.0.1", false)
	body := strings.Repeat("archive-bytes", 100000)
	server := tlsServer(t, cert, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", fmt.Sprint(len(body)))
		io.WriteString(w, body)
	}))
	remote, _ := url.Parse(server.URL)
	tr := trustedTransport(anchor)
	defer tr.CloseIdleConnections()
	bridge := newBridge(remote, tr, "127.0.0.1:12345")
	path := "/updates/v0.14/Tenkaichi3Decomp-windows-x64.zip"
	out := httptest.NewRecorder()
	bridge.ServeHTTP(out, httptest.NewRequest("GET", "http://127.0.0.1:12345"+path, nil))
	if out.Code != 200 || out.Body.String() != body { t.Fatal("archive was truncated", out.Code, out.Body.Len()) }
	for _, path := range []string{"/updates/../config/server.json", "/updates/key.txt", "/updates/v0.14/evil.exe", "/updates/latest.json/extra"} {
		if allowed("GET", path) { t.Fatal("Unexpected path allowed", path) }
	}
	if !allowed("POST", "/v1/watch") { t.Fatal("Existing spectator API blocked") }
}

func TestBridge(t *testing.T) {
	cert, anchor := identity(t, "127.0.0.1", false)
	calls := 0
	server := tlsServer(t, cert, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		raw, _ := io.ReadAll(r.Body)
		if r.Header.Get("X-BT3-Lobby-Key") != "private-test-key" || !bytes.Contains(raw, []byte("玩家")) {
			t.Error("authentication/UTF8 changed")
		}
		if r.Header.Get("X-Real-IP") != "" || r.Header.Get("Cookie") != "" {
			t.Error("untrusted browser/proxy headers forwarded")
		}
		w.Header().Set("Content-Type", "application/json")
		io.WriteString(w, `{"ok":true,"name":"玩家"}`)
	}))
	remote, _ := url.Parse(server.URL)
	tr := trustedTransport(anchor)
	defer tr.CloseIdleConnections()
	bridge := newBridge(remote, tr, "127.0.0.1:12345")
	for _, path := range []string{"/lobby/v1/request", "/directory/v1/request", "/v1/host", "/v1/join", "/v1/poll", "/v1/addrs", "/v1/leave", "/v1/relay"} {
		req := httptest.NewRequest("POST", "http://127.0.0.1:12345"+path, strings.NewReader(`{"name":"玩家"}`))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-BT3-Lobby-Key", "private-test-key")
		req.Header.Set("X-Real-IP", "192.0.2.1")
		req.Header.Set("Cookie", "discard")
		out := httptest.NewRecorder()
		bridge.ServeHTTP(out, req)
		if out.Code != 200 || !strings.Contains(out.Body.String(), "玩家") {
			t.Fatal(out.Code, out.Body.String())
		}
	}
	if calls != 8 {
		t.Fatal(calls)
	}
	for _, item := range []struct{ name, method, path, host, origin, body, ctype string }{
		{name: "host", method: "POST", path: "/lobby/v1/request", host: "evil.example"},
		{name: "origin", method: "POST", path: "/lobby/v1/request", origin: "https://evil.example"},
		{name: "query", method: "POST", path: "/lobby/v1/request?x=1"},
		{name: "path", method: "POST", path: "/unrelated"},
		{name: "method", method: "DELETE", path: "/lobby/v1/request"},
		{name: "get", method: "GET", path: "/directory/v1/request"},
		{name: "large", method: "POST", path: "/lobby/v1/request", body: strings.Repeat("x", 8193)},
		{name: "form", method: "POST", path: "/lobby/v1/request", ctype: "application/x-www-form-urlencoded"},
	} {
		t.Run(item.name, func(t *testing.T) {
			req := httptest.NewRequest(item.method, "http://127.0.0.1:12345"+item.path, strings.NewReader(item.body))
			req.Header.Set("Content-Type", "application/json")
			if item.host != "" {
				req.Host = item.host
			}
			if item.origin != "" {
				req.Header.Set("Origin", item.origin)
			}
			if item.ctype != "" {
				req.Header.Set("Content-Type", item.ctype)
			}
			out := httptest.NewRecorder()
			bridge.ServeHTTP(out, req)
			if out.Code < 400 {
				t.Fatal("request unexpectedly accepted")
			}
		})
	}
	if calls != 8 {
		t.Fatal("rejected requests reached server", calls)
	}
}

func TestRedirectAndOversizeResponse(t *testing.T) {
	for _, kind := range []string{"redirect", "large"} {
		t.Run(kind, func(t *testing.T) {
			cert, anchor := identity(t, "127.0.0.1", false)
			server := tlsServer(t, cert, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if kind == "redirect" {
					http.Redirect(w, r, "https://evil.example", 302)
				} else {
					io.WriteString(w, strings.Repeat("x", 65537))
				}
			}))
			remote, _ := url.Parse(server.URL)
			tr := trustedTransport(anchor)
			defer tr.CloseIdleConnections()
			bridge := newBridge(remote, tr, "127.0.0.1:12345")
			out := httptest.NewRecorder()
			bridge.ServeHTTP(out, httptest.NewRequest("GET", "http://127.0.0.1:12345/healthz", nil))
			if out.Code != 502 {
				t.Fatal(out.Code)
			}
		})
	}
}

func TestCertificateGenerationAndConfig(t *testing.T) {
	dir := t.TempDir()
	if err := generateCertificate("127.0.0.1", dir); err != nil {
		t.Fatal(err)
	}
	if err := generateCertificate("127.0.0.1", dir); err == nil {
		t.Fatal("existing key overwritten")
	}
	raw, _ := os.ReadFile(filepath.Join(dir, "server.crt"))
	block, _ := pem.Decode(raw)
	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		t.Fatal(err)
	}
	if err = cert.VerifyHostname("127.0.0.1"); err != nil {
		t.Fatal(err)
	}
	for _, remote := range []string{"https://127.0.0.1:2626", "http://127.0.0.1:2626", "https://user:pass@127.0.0.1:2626", "https://127.0.0.1:2626/", "https://127.0.0.1:2626?x=1"} {
		raw, _ := json.Marshal(config{Remote: remote, Certificate: "server.crt"})
		path := filepath.Join(dir, "client.json")
		os.WriteFile(path, raw, 0600)
		_, _, _, err := readConfig(path)
		if (err == nil) != (remote == "https://127.0.0.1:2626") {
			t.Fatalf("config %q: %v", remote, err)
		}
	}
}
