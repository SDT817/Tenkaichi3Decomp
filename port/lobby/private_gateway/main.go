// The existing game speaks HTTP to a process-local bridge. Only the bridge
// crosses the Internet, using normal TLS validation with one bundled trust
// anchor. No game packets, system certificate stores or battle code change.
package main

import (
	"bytes"
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"math/big"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

type config struct {
	Remote      string `json:"remote"`
	Certificate string `json:"certificate"`
}

func readConfig(path string) (config, *url.URL, *x509.Certificate, error) {
	var c config
	raw, err := os.ReadFile(path)
	if err != nil {
		return c, nil, nil, err
	}
	if err = json.Unmarshal(raw, &c); err != nil {
		return c, nil, nil, err
	}
	remote, err := url.Parse(c.Remote)
	if err != nil || remote.Scheme != "https" || remote.Host == "" || remote.User != nil ||
		remote.Path != "" || remote.RawQuery != "" || remote.Fragment != "" ||
		remote.Port() == "" || strings.ContainsAny(c.Remote, "\\\r\n\t ") {
		return c, nil, nil, errors.New("invalid private HTTPS endpoint")
	}
	certPath := c.Certificate
	if !filepath.IsAbs(certPath) {
		certPath = filepath.Join(filepath.Dir(path), certPath)
	}
	raw, err = os.ReadFile(certPath)
	if err != nil {
		return c, nil, nil, err
	}
	block, rest := pem.Decode(raw)
	if block == nil || block.Type != "CERTIFICATE" || len(bytes.TrimSpace(rest)) != 0 {
		return c, nil, nil, errors.New("expected one public server certificate")
	}
	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		return c, nil, nil, err
	}
	return c, remote, cert, nil
}

func trustedTransport(cert *x509.Certificate) *http.Transport {
	roots := x509.NewCertPool()
	roots.AddCert(cert)
	// This pool has only our supplied certificate. Hostname, expiry, purpose
	// and signature verification remain enabled; no InsecureSkipVerify.
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.Proxy = nil
	transport.TLSClientConfig = &tls.Config{RootCAs: roots, MinVersion: tls.VersionTLS12}
	transport.DialContext = (&net.Dialer{Timeout: 8 * time.Second, KeepAlive: 30 * time.Second}).DialContext
	transport.TLSHandshakeTimeout = 8 * time.Second
	transport.ResponseHeaderTimeout = 15 * time.Second
	transport.MaxIdleConnsPerHost = 8
	return transport
}

func allowed(method, path string) bool {
	if method == http.MethodGet {
		return path == "/healthz" || updatePath(path)
	}
	if method != http.MethodPost {
		return false
	}
	switch path {
	case "/lobby/v1/request", "/directory/v1/request", "/v1/host", "/v1/join",
		"/v1/poll", "/v1/addrs", "/v1/leave", "/v1/relay", "/v1/watch":
		return true
	}
	return false
}

var updateFile = regexp.MustCompile(`^/updates/v[0-9]+(?:\.[0-9]+){1,3}/Tenkaichi3Decomp-windows-x64\.zip(?:\.sig)?$`)

func updatePath(path string) bool {
	return path == "/updates/latest.json" || path == "/updates/notes.txt" || updateFile.MatchString(path)
}

func newBridge(remote *url.URL, transport *http.Transport, localHost string) http.Handler {
	proxy := &httputil.ReverseProxy{
		Rewrite: func(p *httputil.ProxyRequest) {
			p.SetURL(remote)
			p.Out.Host = remote.Host
			p.Out.Header.Del("Origin")
			p.Out.Header.Del("Cookie")
			p.Out.Header.Del("X-Forwarded-For")
			p.Out.Header.Del("X-Real-IP")
		},
		Transport: transport,
		ErrorLog:  log.New(io.Discard, "", 0),
		ErrorHandler: func(w http.ResponseWriter, _ *http.Request, _ error) {
			// Do not log credentials, JSON bodies, or token-bearing paths.
			http.Error(w, "Private server connection or certificate verification failed.", http.StatusBadGateway)
		},
		ModifyResponse: func(r *http.Response) error {
			if r.StatusCode >= 300 && r.StatusCode < 400 {
				r.Body.Close()
				return errors.New("unexpected server redirect")
			}
			if updatePath(r.Request.URL.Path) {
				// Stream release archives; do not buffer them in the lobby's 64KB
				// JSON response. The game's updater checks size/hash/signature.
				if r.ContentLength < 0 || r.ContentLength > 512<<20 {
					r.Body.Close()
					return errors.New("invalid update response size")
				}
				r.Header.Del("Set-Cookie")
				return nil
			}
			body, err := io.ReadAll(io.LimitReader(r.Body, 65537))
			r.Body.Close()
			if err != nil || len(body) > 65536 {
				return errors.New("invalid server response size")
			}
			r.Body = io.NopCloser(bytes.NewReader(body))
			r.ContentLength = int64(len(body))
			r.Header.Set("Content-Length", fmt.Sprint(len(body)))
			r.Header.Del("Set-Cookie")
			return nil
		},
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		if r.Host != localHost || r.Header.Get("Origin") != "" || r.URL.RawQuery != "" ||
			r.URL.RawPath != "" || !allowed(r.Method, r.URL.Path) {
			http.Error(w, "Local game API only.", http.StatusForbidden)
			return
		}
		if r.Method == http.MethodPost {
			if r.Header.Get("Content-Type") != "application/json" {
				http.Error(w, "JSON required.", http.StatusUnsupportedMediaType)
				return
			}
			body, err := io.ReadAll(io.LimitReader(r.Body, 8193))
			r.Body.Close()
			if err != nil || len(body) > 8192 {
				http.Error(w, "Request too large.", 413)
				return
			}
			r.Body = io.NopCloser(bytes.NewReader(body))
			r.ContentLength = int64(len(body))
		}
		proxy.ServeHTTP(w, r)
	})
}

func health(ctx context.Context, remote *url.URL, transport *http.Transport) error {
	target := *remote
	target.Path = "/healthz"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, target.String(), nil)
	if err != nil {
		return err
	}
	response, err := transport.RoundTrip(req)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	var value struct {
		OK       bool `json:"ok"`
		Protocol int  `json:"protocol"`
	}
	if response.StatusCode != 200 {
		return fmt.Errorf("server health status %d", response.StatusCode)
	}
	if err = json.NewDecoder(io.LimitReader(response.Body, 4096)).Decode(&value); err != nil {
		return err
	}
	if !value.OK || value.Protocol != 6 {
		return errors.New("unexpected private server health response")
	}
	return nil
}

func runBridge(path, game string, args []string, check bool, checkAddress string, desktop bool) error {
	c, remote, cert, err := readConfig(path)
	if err != nil {
		return err
	}
	transport := trustedTransport(cert)
	defer transport.CloseIdleConnections()
	if desktop {
		if err = verifyGameFiles(filepath.Dir(game), c.Remote, transport); err != nil {
			return err
		}
	}
	if checkAddress != "" {
		host, _, parseErr := net.SplitHostPort(checkAddress)
		if !check || parseErr != nil || host != "127.0.0.1" {
			return errors.New("check-address is restricted to a loopback health check")
		}
		transport.DialContext = func(ctx context.Context, network, _ string) (net.Conn, error) {
			return (&net.Dialer{Timeout: 8 * time.Second}).DialContext(ctx, network, checkAddress)
		}
	}
	if check {
		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		err = health(ctx, remote, transport)
		cancel()
		if err != nil {
			return fmt.Errorf("private server HTTPS check failed: %w", err)
		}
		fmt.Println("Private server TLS certificate and health: OK")
		if check {
			return nil
		}
	}
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		return err
	}
	defer listener.Close()
	local := "http://" + listener.Addr().String()
	server := &http.Server{Handler: newBridge(remote, transport, listener.Addr().String()),
		ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 15 * time.Second, IdleTimeout: 30 * time.Second}
	finished := make(chan error, 1)
	go func() { finished <- server.Serve(listener) }()
	defer server.Close()
	if game != "" {
		absolute, err := filepath.Abs(game)
		if err != nil {
			return err
		}
		cmd := exec.Command(absolute, args...)
		cmd.Dir = filepath.Dir(absolute)
		configureDesktopChild(cmd, desktop)
		// Replace inherited bridge variables, rather than append duplicates.
		for _, value := range os.Environ() {
			key := strings.ToUpper(strings.SplitN(value, "=", 2)[0])
			if key != "BT3_LOBBY_GATEWAY_REMOTE" && key != "BT3_LOBBY_GATEWAY_LOCAL" {
				cmd.Env = append(cmd.Env, value)
			}
		}
		cmd.Env = append(cmd.Env, "BT3_LOBBY_GATEWAY_REMOTE="+c.Remote, "BT3_LOBBY_GATEWAY_LOCAL="+local)
		cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, os.Stdout, os.Stderr
		if desktop {
			cmd.Stdin = nil
		}
		return cmd.Run()
	}
	encoded, _ := json.Marshal(map[string]string{"remote": c.Remote, "local": local})
	fmt.Println(string(encoded))
	interrupt := make(chan os.Signal, 1)
	signal.Notify(interrupt, os.Interrupt)
	defer signal.Stop(interrupt)
	select {
	case <-interrupt:
		return nil
	case err := <-finished:
		if err == http.ErrServerClosed {
			return nil
		}
		return err
	}
}

func generateCertificate(ip, folder string) error {
	address := net.ParseIP(ip)
	if address == nil {
		return errors.New("certificate requires a valid IP address")
	}
	if err := os.MkdirAll(folder, 0700); err != nil {
		return err
	}
	for _, name := range []string{"server.crt", "server.key"} {
		if _, err := os.Stat(filepath.Join(folder, name)); !os.IsNotExist(err) {
			return errors.New("certificate files already exist; preserve the existing identity")
		}
	}
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return err
	}
	serial, err := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 128))
	if err != nil {
		return err
	}
	now := time.Now()
	template := &x509.Certificate{SerialNumber: serial, Subject: pkix.Name{CommonName: "BT3 private lobby " + ip},
		NotBefore: now.Add(-24 * time.Hour), NotAfter: now.AddDate(5, 0, 0), IPAddresses: []net.IP{address},
		BasicConstraintsValid: true, KeyUsage: x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	if err != nil {
		return err
	}
	private, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		return err
	}
	if err = os.WriteFile(filepath.Join(folder, "server.key"), pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: private}), 0600); err != nil {
		return err
	}
	if err = os.WriteFile(filepath.Join(folder, "server.crt"), pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}), 0644); err != nil {
		return err
	}
	hash := sha256.Sum256(der)
	fmt.Println("Server certificate SHA256:", hex.EncodeToString(hash[:]))
	fmt.Println("Certificate expiry:", template.NotAfter.UTC().Format(time.RFC3339))
	return nil
}

// Resolve from the launcher, not Explorer's or a shortcut's working directory.
func desktopPaths(executable string) (string, string) {
	dir := filepath.Dir(executable)
	return filepath.Join(dir, "bt3_gateway.json"), filepath.Join(dir, "Tenkaichi3Decomp.exe")
}

func main() {
	configPath := flag.String("config", "bt3_gateway.json", "client configuration")
	game := flag.String("run", "", "start this game while the local bridge is alive")
	check := flag.Bool("check", false, "check pinned HTTPS and health, then exit")
	checkAddress := flag.String("check-address", "", "loopback-only health-check dial address; certificate IP is still verified")
	certIP := flag.String("make-certificate", "", "create a new private server identity for this IP")
	certDir := flag.String("certificate-directory", "", "new private certificate directory")
	repair := flag.Bool("repair", false, "verify and repair this launcher's release files, then exit")
	flag.Parse()
	var err error
	desktop := len(os.Args) == 1
	if desktop {
		var executable string
		executable, err = os.Executable()
		if err == nil {
			*configPath, *game = desktopPaths(executable)
			var output *os.File
			output, err = os.OpenFile(filepath.Join(filepath.Dir(executable), "bt3-launcher.log"), os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0600)
			if err == nil {
				defer output.Close()
				os.Stdout, os.Stderr = output, output
			}
		}
	}
	if err != nil {
		reportDesktopError(err)
		os.Exit(1)
	}
	if *repair {
		var executable string
		executable, err = os.Executable()
		if err == nil {
			c, _, cert, configErr := readConfig(*configPath)
			err = configErr
			if err == nil {
				transport := trustedTransport(cert)
				defer transport.CloseIdleConnections()
				err = verifyGameFiles(filepath.Dir(executable), c.Remote, transport)
			}
		}
	} else if *certIP != "" {
		err = generateCertificate(*certIP, *certDir)
	} else {
		err = runBridge(*configPath, *game, flag.Args(), *check, *checkAddress, desktop)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "BT3 connection:", err)
		if desktop {
			reportDesktopError(err)
		}
		os.Exit(1)
	}
}
